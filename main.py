import asyncio
import json
import logging
import io
import os
import uuid
import tempfile
import httpx
import traceback
import re
from datetime import datetime
from fastapi import FastAPI, WebSocket, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import websockets
from pydub import AudioSegment
from pydub.utils import mediainfo
import ollama
from openai import AsyncOpenAI
import anthropic
# import google.generativeai as genai  # Descomenta para usar Google Gemini
from config import (
    HOST, PORT, LOG_LEVEL,
    DEEPGRAM_API_KEY,
    DEEPGRAM_LANGUAGE, DEEPGRAM_MODEL, DEEPGRAM_PUNCTUATE,
    ASSEMBLYAI_API_KEY,
    OPENAI_API_KEY,
    ANTHROPIC_API_KEY,
    # GEMINI_API_KEY,  # Descomenta para usar Google Gemini
)

# ========== IMPORTAR BASE DE DATOS ==========
from pacientes_db import cargar_base_datos, buscar_cedula_flexible

logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Copiloto Médico", version="6.4.0")

# ========== CARGAR BASE DE DATOS DE PACIENTES ==========
# Intentar múltiples rutas para mayor robustez
POSSIBLE_PATHS = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "Bases de datos Prototipo Copiloto admisión.xlsx"),
    os.path.join(os.getcwd(), "data", "Bases de datos Prototipo Copiloto admisión.xlsx"),
    r"C:\Users\Angela\Documents\8 Octavo Semestre\IA 2\Proyecto coomeva\medical-copilot\data\Bases de datos Prototipo Copiloto admisión.xlsx"
]

EXCEL_PATH = None
for path in POSSIBLE_PATHS:
    if os.path.exists(path):
        EXCEL_PATH = path
        break

if not EXCEL_PATH:
    EXCEL_PATH = POSSIBLE_PATHS[0]  # Use first path as default

logger.info(f"[INFO] Rutas probadas:")
for path in POSSIBLE_PATHS:
    logger.info(f"  - {path} (existe: {os.path.exists(path)})")
logger.info(f"[INFO] Ruta seleccionada: {EXCEL_PATH}")

PACIENTES_DB = cargar_base_datos(EXCEL_PATH)

if PACIENTES_DB:
    logger.info(f"[SUCCESS] Base de datos cargada: {len(PACIENTES_DB)} pacientes")
    for cedula, p in PACIENTES_DB.items():
        logger.info(f"   - {cedula}: {p['nombre']}")
else:
    logger.error("[ERROR] Base de datos NO cargada - verificar ruta del Excel")
    logger.error(f"[ERROR] Ruta intentada: {EXCEL_PATH}")

# Conexiones WebSocket activas: { websocket_id: WebSocket }
active_connections = {}


# ========== EXTRACTOR JSON ROBUSTO ==========
def extract_json(text: str) -> dict:
    """Extrae JSON de texto, manejando formatos mal formados.

    Intenta múltiples estrategias:
    1. Parse directo
    2. Buscar JSON entre llaves
    3. Limpiar caracteres problemáticos
    4. Retornar estructura por defecto si todo falla
    """
    try:
        # Intento 1: parsear directo
        return json.loads(text)
    except Exception as e:
        logger.debug(f"Parse directo falló: {e}")

    try:
        # Intento 2: buscar JSON entre llaves
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        logger.debug(f"Buscar entre llaves falló: {e}")

    try:
        # Intento 3: limpiar caracteres problemáticos y reintentar
        cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if match:
            json_str = match.group()
            logger.debug(f"JSON limpiado: {json_str[:200]}...")
            return json.loads(json_str)
    except Exception as e:
        logger.debug(f"Limpieza y parse falló: {e}")

    # Retornar estructura por defecto si todo falla
    logger.warning(f"[WARNING] No se pudo extraer JSON de: {text[:100]}...")
    return {
        "cedula_detectada": None,
        "preguntas_sugeridas": ["¿Cuál es el motivo de su llamada?"],
        "datos_paciente": {"nombre": None, "sintomas": [], "medicamentos": [], "alergias": []},
        "nivel_riesgo": "bajo",
        "alertas": [],
        "resumen": "Analizando..."
    }


# ========== ANÁLISIS CON OPENAI/GPT-3.5 ==========
async def analyze_with_openai(transcript_text: str) -> dict:
    """Analizar transcripción con OpenAI GPT-3.5-turbo

    Extrae:
    - Preguntas sugeridas para seguimiento
    - Clasificación del paciente
    - Datos del paciente
    - Nivel de riesgo
    - Alertas importantes
    - Siguiente paso recomendado
    """
    try:
        logger.info("🤖 Iniciando análisis con OpenAI (GPT-3.5-turbo)...")

        client = AsyncOpenAI(api_key=OPENAI_API_KEY)

        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "Eres un asistente especializado en admisión médica telefónica. Responde SOLO con JSON válido, sin texto adicional."
                },
                {
                    "role": "user",
                    "content": f"""Analiza esta transcripción de llamada médica y responde SOLO con JSON:

TRANSCRIPCIÓN:
{transcript_text}

IMPORTANTE para cedula_detectada:
- IGNORA COMPLETAMENTE: 'sí', 'si', 'no', 'eh', 'este', 'pues', 'o sea', 'bueno', 'mira', 'buenas' (muletillas/confirmaciones)
- El paciente dicta su cédula: solo palabras numéricas
- 'once' = dos dígitos: 1,1 (NO el número 11)
- 'treinta' = dos dígitos: 3,0 (NO el número 30)
- 'veinte' = dos dígitos: 2,0 (NO el número 20)
- Cada palabra numérica se convierte a sus dígitos individuales
- Cédulas colombianas: máximo 10 dígitos
- Si obtienes >10 dígitos después de filtrar, revisaste mal

JSON requerido:
{{
  "cedula_detectada": "solo números si detectada (máx 10 dígitos), null si no",
  "preguntas_sugeridas": ["pregunta1", "pregunta2", "pregunta3"],
  "datos_paciente": {{
    "nombre": null,
    "sintomas": [],
    "medicamentos": [],
    "alergias": []
  }},
  "nivel_riesgo": "bajo|medio|alto|crítico",
  "alertas": [],
  "resumen": "resumen breve de la llamada"
}}"""
                }
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )

        text = response.choices[0].message.content
        logger.debug(f"Respuesta OpenAI: {text[:200]}...")

        # Extraer JSON con función robusta
        analysis = extract_json(text)
        logger.info(f"✅ Análisis OpenAI completado - Riesgo: {analysis.get('nivel_riesgo', 'desconocido')}")

        return analysis

    except Exception as e:
        logger.error(f"❌ Error en análisis OpenAI: {e}")
        logger.info("⚠️ Fallback a Ollama...")
        return await analyze_with_ollama(transcript_text)


# ========== ANÁLISIS CON ANTHROPIC CLAUDE ==========
async def analyze_with_claude(transcript_text: str) -> dict:
    """Analizar transcripción con Claude (Anthropic)

    Extrae:
    - Preguntas sugeridas para seguimiento
    - Datos del paciente
    - Nivel de riesgo
    - Alertas importantes
    - Resumen de la llamada
    """
    try:
        logger.info("🤖 Iniciando análisis con Claude (Anthropic)...")

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                system="Eres un asistente especializado en admisión médica telefónica. Responde SOLO con JSON válido, sin texto adicional ni markdown.",
                messages=[{
                    "role": "user",
                    "content": f"""Analiza esta transcripción de llamada médica:

TRANSCRIPCIÓN:
{transcript_text}

IMPORTANTE para cedula_detectada:
- IGNORA COMPLETAMENTE: 'sí', 'si', 'no', 'eh', 'este', 'pues', 'o sea', 'bueno', 'mira', 'buenas' (muletillas/confirmaciones)
- El paciente dicta su cédula: solo palabras numéricas
- 'once' = dos dígitos: 1,1 (NO el número 11)
- 'treinta' = dos dígitos: 3,0 (NO el número 30)
- 'veinte' = dos dígitos: 2,0 (NO el número 20)
- Cada palabra numérica se convierte a sus dígitos individuales
- Cédulas colombianas: máximo 10 dígitos
- Si obtienes >10 dígitos después de filtrar, revisaste mal

Responde SOLO con este JSON:
{{
  "cedula_detectada": "solo números si detectada (máx 10 dígitos), null si no",
  "preguntas_sugeridas": ["pregunta1", "pregunta2", "pregunta3"],
  "datos_paciente": {{
    "nombre": null,
    "sintomas": [],
    "medicamentos": [],
    "alergias": []
  }},
  "nivel_riesgo": "bajo|medio|alto|crítico",
  "alertas": [],
  "resumen": "resumen breve de la llamada"
}}"""
                }]
            )
        )

        text = response.content[0].text
        # Limpiar markdown si existe
        text = re.sub(r'```json\n?', '', text)
        text = re.sub(r'```\n?', '', text)
        text = text.strip()

        logger.debug(f"Respuesta Claude: {text[:200]}...")

        # Extraer JSON
        analysis = extract_json(text)
        logger.info(f"✅ Análisis Claude completado - Riesgo: {analysis.get('nivel_riesgo', 'desconocido')}")

        return analysis

    except Exception as e:
        logger.error(f"❌ Error en análisis Claude: {e}")
        logger.info("⚠️ Fallback a Ollama...")
        return await analyze_with_ollama(transcript_text)


# ========== ANÁLISIS CON GOOGLE GEMINI (COMENTADO - DESCOMENTA PARA USAR) ==========
# async def analyze_with_gemini(transcript_text: str) -> dict:
#     """Analizar transcripción con Google Gemini API
#
#     Extrae:
#     - Preguntas sugeridas para seguimiento
#     - Datos del paciente
#     - Nivel de riesgo
#     - Alertas importantes
#     - Resumen de la llamada
#     """
#     try:
#         logger.info("🤖 Iniciando análisis con Google Gemini (gemini-1.5-flash)...")
#
#         genai.configure(api_key=GEMINI_API_KEY)
#         model = genai.GenerativeModel('gemini-1.5-flash')
#
#         prompt = f"""Eres un asistente especializado en admisión médica telefónica.
# Analiza esta transcripción de llamada médica y responde SOLO con JSON válido, sin texto adicional.
#
# TRANSCRIPCIÓN:
# {transcript_text}
#
# JSON requerido (responde EXACTAMENTE así):
# {{
#   "preguntas_sugeridas": ["pregunta1", "pregunta2", "pregunta3"],
#   "datos_paciente": {{
#     "nombre": null,
#     "sintomas": [],
#     "medicamentos": [],
#     "alergias": []
#   }},
#   "nivel_riesgo": "bajo|medio|alto|crítico",
#   "alertas": [],
#   "resumen": "resumen breve de la llamada"
# }}"""
#
#         # Llamar a Gemini (usar executor para no bloquear)
#         loop = asyncio.get_event_loop()
#         response = await loop.run_in_executor(
#             None,
#             lambda: model.generate_content(prompt)
#         )
#
#         text = response.text
#         logger.debug(f"Respuesta Gemini: {text[:200]}...")
#
#         # Limpiar markdown si existe
#         text = re.sub(r'```json\n?', '', text)
#         text = re.sub(r'```\n?', '', text)
#
#         # Extraer JSON con función robusta
#         analysis = extract_json(text)
#         logger.info(f"✅ Análisis Gemini completado - Riesgo: {analysis.get('nivel_riesgo', 'desconocido')}")
#
#         return analysis
#
#     except Exception as e:
#         logger.error(f"❌ Error en análisis Gemini: {e}")
#         logger.info("⚠️ Fallback a OpenAI...")
#         # Fallback a OpenAI si Gemini falla
#         if OPENAI_API_KEY:
#             return await analyze_with_openai(transcript_text)
#         else:
#             return await analyze_with_ollama(transcript_text)


# ========== FUNCIÓN PRINCIPAL DE ANÁLISIS ==========
async def analyze(transcript_text: str) -> dict:
    """Selector de análisis: Claude > Gemini > OpenAI > Ollama

    Prioridad:
    1. Claude/Anthropic (si ANTHROPIC_API_KEY está configurada)
    2. Google Gemini (si GEMINI_API_KEY está configurada)
    3. OpenAI (si OPENAI_API_KEY está configurada)
    4. Ollama (fallback local gratuito)
    """
    if ANTHROPIC_API_KEY:
        logger.debug("📊 Usando Claude (Anthropic) para análisis (prioridad 1)")
        return await analyze_with_claude(transcript_text)
    # elif GEMINI_API_KEY:
    #     logger.debug("📊 Usando Gemini para análisis (prioridad 2)")
    #     return await analyze_with_gemini(transcript_text)
    elif OPENAI_API_KEY:
        logger.debug("📊 Usando OpenAI para análisis (prioridad 3)")
        return await analyze_with_openai(transcript_text)
    else:
        logger.debug("📊 Usando Ollama para análisis (prioridad 4, fallback)")
        return await analyze_with_ollama(transcript_text)


# ========== ANÁLISIS CON OLLAMA/LLAMA3.2 ==========
async def analyze_with_ollama(transcript_text: str) -> dict:
    """Analizar transcripción con Ollama usando llama3.2

    Extrae:
    - Preguntas sugeridas para seguimiento
    - Datos del paciente (nombre, síntomas, medicamentos, alergias)
    - Nivel de riesgo
    - Alertas importantes
    - Resumen de la llamada
    """
    try:
        logger.info("🤖 Iniciando análisis con Ollama (llama3.2)...")

        prompt = f"""Eres un asistente de admisión médica inteligente.
Analiza esta transcripción de llamada médica y extrae información relevante.

TRANSCRIPCIÓN:
{transcript_text}

Responde EXACTAMENTE con este JSON válido, sin texto adicional:
{{
  "preguntas_sugeridas": ["pregunta1", "pregunta2", "pregunta3"],
  "datos_paciente": {{
    "nombre": null,
    "sintomas": [],
    "medicamentos": [],
    "alergias": []
  }},
  "nivel_riesgo": "bajo",
  "alertas": [],
  "resumen": "resumen breve de la llamada"
}}"""

        # Llamar a Ollama (asincrónico)
        response = await asyncio.to_thread(
            ollama.chat,
            model="llama3.2",
            messages=[{"role": "user", "content": prompt}],
            stream=False
        )

        text = response['message']['content']
        logger.debug(f"Respuesta Ollama: {text[:200]}...")

        # Extraer JSON con función robusta
        analysis = extract_json(text)
        logger.info(f"✅ Análisis completado - Riesgo: {analysis.get('nivel_riesgo', 'desconocido')}")

        return analysis

    except Exception as e:
        logger.error(f"❌ Error en análisis Ollama: {e}")
        return {
            "preguntas_sugeridas": ["¿Cuál es el motivo de su llamada?"],
            "datos_paciente": {"nombre": None, "sintomas": [], "medicamentos": [], "alergias": []},
            "nivel_riesgo": "bajo",
            "alertas": [],
            "resumen": "Analizando..."
        }

if not ASSEMBLYAI_API_KEY:
    logger.error("❌ ASSEMBLYAI_API_KEY no configurada en .env")

# Deepgram maneja diarización directamente vía REST API
# No se necesita pipeline local


# Endpoints HTTP

@app.get("/")
async def get_index():
    """Sirve la página HTML principal"""
    return FileResponse("index.html", media_type="text/html")


@app.get("/api/health")
async def health_check():
    """Health check del servidor"""
    return JSONResponse({
        "status": "healthy",
        "server": {
            "version": "6.2.0",
            "host": HOST,
            "port": PORT
        },
        "transcription": {
            "configured": bool(ASSEMBLYAI_API_KEY),
            "method": "assemblyai",
            "mode": "batch processing"
        },
        "diarization": {
            "enabled": bool(ASSEMBLYAI_API_KEY),
            "method": "assemblyai_speaker_labels"
        },
        "timestamp": datetime.now().isoformat()
    })


@app.get("/bd-status")
async def bd_status():
    """Estado de la base de datos de pacientes"""
    logger.debug(f"[DEBUG] /bd-status llamado - PACIENTES_DB len: {len(PACIENTES_DB)}")
    return JSONResponse({
        "cargada": len(PACIENTES_DB) > 0,
        "total_pacientes": len(PACIENTES_DB),
        "pacientes": [
            {"cedula": k, "nombre": v["nombre"]}
            for k, v in PACIENTES_DB.items()
        ]
    })


@app.get("/debug-db")
async def debug_db():
    """Endpoint de debug - Info sobre BD"""
    return JSONResponse({
        "PACIENTES_DB_len": len(PACIENTES_DB),
        "PACIENTES_DB_type": str(type(PACIENTES_DB)),
        "EXCEL_PATH": EXCEL_PATH,
        "EXCEL_EXISTS": os.path.exists(EXCEL_PATH),
        "PACIENTES_DB_keys": list(PACIENTES_DB.keys())
    })


@app.get("/paciente/{cedula}")
async def buscar_paciente(cedula: str):
    """Buscar paciente por cédula en la base de datos (RÁPIDO - sin logs innecesarios)"""
    cedula_limpia = cedula.strip()

    # Búsqueda exacta primero (O(1))
    paciente = PACIENTES_DB.get(cedula_limpia)
    if paciente:
        return JSONResponse({
            "found": True,
            "paciente": paciente
        })

    # Si no encuentra exacta, probar búsqueda flexible
    paciente = buscar_cedula_flexible(cedula_limpia, PACIENTES_DB)
    if paciente:
        return JSONResponse({
            "found": True,
            "paciente": paciente
        })

    # No encontrado - respuesta silenciosa
    return JSONResponse({
        "found": False,
        "message": f"No se encontró paciente con cédula: {cedula_limpia}"
    })


@app.get("/paciente/nombre/{nombre}")
async def buscar_paciente_por_nombre(nombre: str):
    """Buscar paciente por nombre en la base de datos"""
    nombre_lower = nombre.lower().strip()

    for cedula, paciente in PACIENTES_DB.items():
        if nombre_lower in paciente["nombre"].lower():
            logger.info(f"[SUCCESS] Paciente encontrado por nombre: {nombre}")
            return JSONResponse({
                "found": True,
                "paciente": paciente
            })

    logger.warning(f"[WARNING] Paciente no encontrado por nombre: {nombre}")
    return JSONResponse({
        "found": False,
        "message": f"No se encontró paciente con nombre: {nombre}"
    })


# DEEPGRAM - DESACTIVADO TEMPORALMENTE
# async def transcribe_with_diarization_deepgram(audio_data: bytes) -> list:
#     """Transcribir con diarización usando Deepgram REST API
#
#     Parámetros:
#     - diarize=true: Activar diarización
#     - utterances=true: Retornar utterances
#     - utt_split=0.8: Separar utterances cada 0.8s sin habla
#
#     Retorna: lista de utterances con {transcript, speaker, start, end}
#     """
#     try:
#         logger.info("🎤 Enviando audio a Deepgram con diarización...")
#
#         url = "https://api.deepgram.com/v1/listen"
#
#         params = {
#             "model": DEEPGRAM_MODEL,
#             "language": DEEPGRAM_LANGUAGE,
#             "diarize": "true",
#             "utterances": "true",
#             "utt_split": "0.8",
#             "punctuate": DEEPGRAM_PUNCTUATE,
#         }
#
#         headers = {
#             "Authorization": f"Token {DEEPGRAM_API_KEY}",
#             "Content-Type": "application/octet-stream"
#         }
#
#         # Usar httpx para enviar archivo completo
#         async with httpx.AsyncClient(timeout=300) as client:
#             response = await client.post(
#                 url,
#                 params=params,
#                 headers=headers,
#                 content=audio_data
#             )
#
#         if response.status_code == 200:
#             result = response.json()
#             utterances = result.get("results", {}).get("utterances", [])
#
#             logger.info(f"✅ Deepgram retornó {len(utterances)} utterances")
#
#             # Procesar utterances
#             processed = []
#             for utt in utterances:
#                 processed.append({
#                     "transcript": utt.get("transcript", ""),
#                     "speaker": utt.get("speaker", 0),
#                     "start": utt.get("start", 0),
#                     "end": utt.get("end", 0)
#                 })
#
#             return processed
#         else:
#             logger.error(f"❌ Deepgram error {response.status_code}: {response.text}")
#             return []
#
#     except Exception as e:
#         logger.error(f"❌ Error en diarización Deepgram: {e}")
#         return []


# DEEPGRAM STREAMING - Nueva arquitectura
async def deepgram_streaming_handler(client_ws: WebSocket, ws_id: str):
    """Maneja streaming de audio Deepgram en tiempo real

    Flujo:
    1. Frontend envía chunks de audio PCM 16bit 16000Hz via WebSocket
    2. Backend conecta a Deepgram WebSocket
    3. Reenvía chunks a Deepgram
    4. Recibe transcripciones en tiempo real
    5. Reenvía al frontend sincronizado con currentTime
    """
    # Conectar a Deepgram WebSocket
    # Nota: El sample_rate debe coincidir con el del frontend (48000 Hz típicamente)
    # La URL aquí es genérica, pero el frontend está codificando a su sample rate original
    deepgram_url = "wss://api.deepgram.com/v1/listen"
    deepgram_params = {
        "model": DEEPGRAM_MODEL,
        "language": DEEPGRAM_LANGUAGE,
        "diarize": "true",
        "encoding": "linear16",
        "sample_rate": "16000",  # Audio resampled by frontend to 16000 Hz
        "punctuate": DEEPGRAM_PUNCTUATE,
        "smart_format": "true",
    }

    # Construir URL con parámetros
    params_str = "&".join([f"{k}={v}" for k, v in deepgram_params.items()])
    deepgram_ws_url = f"{deepgram_url}?{params_str}"

    logger.info(f"🔗 Conectando a Deepgram WebSocket para {ws_id}")
    logger.info(f"📍 URL: {deepgram_ws_url}")

    try:
        async with websockets.connect(
            deepgram_ws_url,
            additional_headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"}
        ) as deepgram_ws:
            logger.info(f"✅ Conectado a Deepgram para {ws_id}")

            # Enviar mensaje de inicialización a Deepgram (algunos APIs lo necesitan)
            try:
                init_message = json.dumps({"type": "Start"})
                await deepgram_ws.send(init_message)
                logger.debug(f"📨 Mensaje de inicialización enviado a Deepgram")
            except Exception as e:
                logger.debug(f"Nota: Mensaje de inicio no soportado por Deepgram: {e}")

            # Task para recibir desde frontend y enviar a Deepgram
            async def send_to_deepgram():
                logger.info(f"📡 Iniciando recepción de chunks del cliente {ws_id}")
                chunk_count = 0
                try:
                    while True:
                        try:
                            # Recibir mensaje del frontend (puede ser binario o texto)
                            logger.debug(f"⏳ Esperando mensaje del cliente...")
                            message = await asyncio.wait_for(
                                client_ws.receive(),
                                timeout=300.0
                            )
                            logger.debug(f"✓ Mensaje recibido: {list(message.keys())}")

                            # Solo procesar datos binarios (audio)
                            if "bytes" in message:
                                data = message["bytes"]
                                chunk_count += 1
                                logger.info(f"📥 Chunk #{chunk_count} recibido: {len(data)} bytes")
                                # Enviar audio binario a Deepgram
                                await deepgram_ws.send(data)
                                logger.debug(f"📤 Chunk #{chunk_count} reenviado a Deepgram ({len(data)} bytes)")
                            elif "text" in message:
                                msg_text = message.get('text', '')
                                logger.debug(f"Mensaje texto: {msg_text[:50]}")

                                # Si el cliente envía "close" o "end", cerrar el stream a Deepgram
                                if msg_text.lower() in ['close', 'end', 'finish']:
                                    logger.info(f"📤 Enviando señal de fin de stream a Deepgram")
                                    await deepgram_ws.send(json.dumps({"type": "CloseStream"}))
                                    break

                        except asyncio.TimeoutError:
                            logger.info(f"⏱️ Timeout esperando chunks (300s sin datos)")
                            # Enviar señal de cierre a Deepgram
                            try:
                                await deepgram_ws.send(json.dumps({"type": "CloseStream"}))
                            except:
                                pass
                            break
                except RuntimeError as e:
                    if "disconnect message" in str(e):
                        logger.info(f"📴 Cliente {ws_id} desconectado (chunks recibidos: {chunk_count})")
                        # Intentar enviar cierre a Deepgram
                        try:
                            await deepgram_ws.send(json.dumps({"type": "CloseStream"}))
                        except:
                            pass
                    else:
                        logger.error(f"❌ RuntimeError: {e}")
                except Exception as e:
                    logger.error(f"❌ Error en send_to_deepgram: {type(e).__name__}: {e}")

            # Task para recibir desde Deepgram y enviar al frontend
            async def receive_from_deepgram():
                try:
                    async for message in deepgram_ws:
                        try:
                            result = json.loads(message)

                            # Procesar respuesta de Deepgram
                            if "results" in result:
                                alternatives = result.get("results", {}).get("alternatives", [])
                                if alternatives:
                                    transcript = alternatives[0].get("transcript", "")

                                    if transcript:
                                        # Enviar al frontend
                                        await client_ws.send_json({
                                            "type": "transcription",
                                            "text": transcript,
                                            "is_final": result.get("is_final", False),
                                            "duration": result.get("duration", 0)
                                        })
                                        logger.info(f"✅ Transcripción: {transcript}")
                        except json.JSONDecodeError:
                            logger.debug(f"Mensaje no-JSON de Deepgram: {message[:50]}")
                except Exception as e:
                    logger.error(f"❌ Error recibiendo de Deepgram: {e}")

            # Ejecutar ambas tasks en paralelo
            await asyncio.gather(
                send_to_deepgram(),
                receive_from_deepgram()
            )

    except Exception as e:
        logger.error(f"❌ Error en streaming Deepgram: {e}")
        try:
            await client_ws.send_json({
                "type": "error",
                "message": f"Error Deepgram: {str(e)}"
            })
        except:
            pass


# ASSEMBLYAI - DESACTIVADO TEMPORALMENTE (Fallback)
async def transcribe_with_assemblyai(audio_data: bytes, client_ws):
    """Transcribir con diarización usando AssemblyAI REST API

    Flujo:
    1. Subir audio a AssemblyAI
    2. Solicitar transcripción con speaker_labels=True
    3. Hacer polling hasta completar
    4. Procesar utterances y enviar al frontend
    """
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            # 1. Subir el archivo de audio
            logger.info("📤 Subiendo audio a AssemblyAI...")
            upload_response = await client.post(
                "https://api.assemblyai.com/v2/upload",
                headers={"authorization": ASSEMBLYAI_API_KEY},
                content=audio_data
            )

            if upload_response.status_code != 200:
                logger.error(f"❌ Error subiendo a AssemblyAI: {upload_response.text}")
                return False

            upload_url = upload_response.json()["upload_url"]
            logger.info(f"✅ Audio subido: {upload_url}")

            # 2. Solicitar transcripción con diarización
            logger.info("🎯 Solicitando transcripción con diarización...")
            if client_ws:
                await client_ws.send_json({
                    "type": "status",
                    "message": "Enviando audio a AssemblyAI para procesamiento..."
                })

            transcript_response = await client.post(
                "https://api.assemblyai.com/v2/transcript",
                headers={"authorization": ASSEMBLYAI_API_KEY},
                json={
                    "audio_url": upload_url,
                    "speech_models": ["universal"],
                    "language_code": "es",
                    "speaker_labels": True,
                    "speakers_expected": 2
                }
            )

            if transcript_response.status_code != 200:
                logger.error(f"❌ Error solicitando transcripción: {transcript_response.text}")
                return False

            transcript_id = transcript_response.json()["id"]
            logger.info(f"📝 ID de transcripción: {transcript_id}")

            # 3. Polling hasta que esté listo
            logger.info("⏳ Esperando procesamiento de AssemblyAI...")
            poll_count = 0
            while True:
                result = await client.get(
                    f"https://api.assemblyai.com/v2/transcript/{transcript_id}",
                    headers={"authorization": ASSEMBLYAI_API_KEY}
                )
                data = result.json()
                status = data.get("status")

                poll_count += 1
                logger.debug(f"Poll #{poll_count}: status={status}")

                # Notificar progreso al frontend
                if client_ws:
                    await client_ws.send_json({
                        "type": "status",
                        "message": f"Analizando audio... ({status})"
                    })

                if status == "completed":
                    logger.info("✅ Transcripción completada")
                    utterances = data.get("utterances", [])
                    logger.info(f"📊 {len(utterances)} utterances detectadas")

                    # Acumular texto para análisis progresivo
                    full_transcript = ""
                    utterances_count = 0

                    # Procesar y enviar utterances
                    for i, utt in enumerate(utterances):
                        # Convertir speaker label (A, B, etc.) a número (0, 1, etc.)
                        speaker = ord(utt.get("speaker", "A")) - ord("A")
                        text = utt.get("text", "").strip()
                        speaker_name = "Paciente" if speaker == 0 else "Doctor"

                        if text and client_ws:
                            # Acumular para análisis progresivo
                            full_transcript += f"{speaker_name}: {text}\n"
                            utterances_count += 1

                            # Con AssemblyAI batch, todos los utterances están disponibles
                            # Marcar el PRIMERO como final para que el frontend muestre el chat inmediatamente
                            is_final = (i == 0) or (i == len(utterances) - 1)
                            await client_ws.send_json({
                                "type": "transcription",
                                "text": text,
                                "speaker": speaker,
                                "start": utt.get("start", 0) / 1000,
                                "end": utt.get("end", 0) / 1000,
                                "is_final": is_final
                            })
                            logger.info(f"✅ Speaker {speaker}: {text[:50]}... (final: {is_final})")

                    return True

                elif status == "error":
                    logger.error(f"❌ Error en AssemblyAI: {data.get('error')}")
                    if client_ws:
                        await client_ws.send_json({
                            "type": "error",
                            "message": "Error en transcripción de AssemblyAI"
                        })
                    return False

                # Esperar antes de siguiente polling
                await asyncio.sleep(2)

    except Exception as e:
        logger.error(f"❌ Error en AssemblyAI: {e}")
        if client_ws:
            try:
                await client_ws.send_json({
                    "type": "error",
                    "message": f"Error: {str(e)}"
                })
            except:
                pass
        return False


@app.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    websocket_id: str = Form(...)
):
    """Transcribe un archivo usando AssemblyAI con diarización integrada"""
    try:
        logger.info(f"📤 Archivo: {file.filename}, WebSocket ID: {websocket_id}")

        # Verificar que el cliente está conectado
        client_ws = active_connections.get(websocket_id)
        if not client_ws:
            logger.warning(f"❌ WebSocket {websocket_id} no encontrado")
            return JSONResponse({
                "status": "error",
                "message": "WebSocket no conectado"
            }, status_code=400)

        if not ASSEMBLYAI_API_KEY:
            logger.error("❌ ASSEMBLYAI_API_KEY no configurada")
            await client_ws.send_json({
                "type": "error",
                "message": "AssemblyAI no configurado"
            })
            return JSONResponse({
                "status": "error",
                "message": "AssemblyAI no configurado"
            }, status_code=500)

        # Leer archivo
        audio_data = await file.read()
        logger.info(f"📦 Tamaño archivo: {len(audio_data)} bytes")

        await client_ws.send_json({
            "type": "status",
            "message": f"Procesando archivo: {file.filename}"
        })

        # Convertir a PCM 16bit 16000Hz
        logger.info("🔄 Convirtiendo audio a PCM 16bit 16000Hz...")
        audio = AudioSegment.from_file(io.BytesIO(audio_data))
        audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)

        # Exportar a bytes en formato WAV
        buffer = io.BytesIO()
        audio.export(buffer, format="wav")
        converted_audio = buffer.getvalue()

        logger.info(f"✅ Audio convertido: {len(converted_audio)} bytes")

        await client_ws.send_json({
            "type": "status",
            "message": "Audio convertido. Analizando audio..."
        })

        # TRANSCRIPCIÓN + DIARIZACIÓN CON ASSEMBLYAI
        success = await transcribe_with_assemblyai(converted_audio, client_ws)

        if not success:
            return JSONResponse({
                "status": "error",
                "message": "Error procesando con AssemblyAI"
            }, status_code=500)

        logger.info("✅ Transcripción completada")
        await client_ws.send_json({
            "type": "status",
            "message": "Transcripción completada"
        })

        return JSONResponse({
            "status": "success",
            "message": "Transcripción procesada con AssemblyAI"
        })

    except Exception as e:
        logger.error(f"❌ Error en transcribe: {e}")
        try:
            await client_ws.send_json({
                "type": "error",
                "message": f"Error: {str(e)}"
            })
        except:
            pass
        return JSONResponse({
            "status": "error",
            "message": str(e)
        }, status_code=500)


# WebSockets

@app.websocket("/ws/audio-stream")
async def websocket_audio_stream(websocket: WebSocket):
    """WebSocket para transcripción con AssemblyAI (batch processing)

    Flujo:
    1. Frontend sube archivo completo
    2. Backend envía a AssemblyAI
    3. Backend hace polling con status updates
    4. Cuando está listo, envía transcripciones al frontend
    5. Frontend pausa audio automáticamente
    """
    await websocket.accept()

    # Generar ID único para esta sesión
    ws_id = str(uuid.uuid4())
    active_connections[ws_id] = websocket
    logger.info(f"🌐 Cliente conectado: {ws_id}")

    try:
        # Enviar ID al cliente
        await websocket.send_json({
            "type": "session_id",
            "id": ws_id
        })

        logger.info(f"📤 Session ID enviado: {ws_id}")

        # Esperar archivo de audio del frontend
        while True:
            try:
                message = await asyncio.wait_for(
                    websocket.receive(),
                    timeout=300.0
                )

                # Procesar bytes de audio
                if "bytes" in message:
                    audio_data = message["bytes"]
                    logger.info(f"📥 Audio recibido: {len(audio_data)} bytes")

                    await websocket.send_json({
                        "type": "status",
                        "message": "Audio recibido. Procesando..."
                    })

                    # Convertir a PCM 16bit 16000Hz
                    logger.info("🔄 Convirtiendo audio a PCM 16bit 16000Hz...")
                    try:
                        audio = AudioSegment.from_file(io.BytesIO(audio_data))
                        audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)

                        # Exportar a bytes en formato WAV
                        buffer = io.BytesIO()
                        audio.export(buffer, format="wav")
                        converted_audio = buffer.getvalue()

                        logger.info(f"✅ Audio convertido: {len(converted_audio)} bytes")

                        # Transcribir con AssemblyAI
                        await transcribe_with_assemblyai(converted_audio, websocket)

                    except Exception as e:
                        logger.error(f"❌ Error procesando audio: {e}")
                        await websocket.send_json({
                            "type": "error",
                            "message": f"Error procesando audio: {str(e)}"
                        })

                elif "text" in message:
                    try:
                        data = json.loads(message.get("text", "{}"))

                        # Análisis BAJO DEMANDA desde el frontend
                        if data.get("type") == "analyze":
                            transcript_text = data.get("text", "")
                            logger.info(f"[INFO] Análisis bajo demanda: {len(transcript_text)} caracteres")

                            try:
                                analysis = await analyze(transcript_text)

                                # Enviar cédula detectada si existe
                                cedula_detectada = analysis.get("cedula_detectada")
                                if cedula_detectada:
                                    logger.info(f"[SUCCESS] Cédula detectada por IA: {cedula_detectada}")
                                    await websocket.send_json({
                                        "type": "cedula_detectada",
                                        "cedula": cedula_detectada
                                    })

                                await websocket.send_json({
                                    "type": "analysis",
                                    "data": analysis,
                                    "progressive": True
                                })
                                logger.info(f"[SUCCESS] Análisis enviado al frontend")
                            except Exception as e:
                                logger.error(f"[ERROR] Error en análisis: {e}")
                                # Enviar análisis por defecto con al menos una pregunta
                                await websocket.send_json({
                                    "type": "analysis",
                                    "data": {
                                        "cedula_detectada": None,
                                        "preguntas_sugeridas": ["¿Cuál es el motivo de su llamada?"],
                                        "datos_paciente": {"nombre": None, "sintomas": [], "medicamentos": [], "alergias": []},
                                        "nivel_riesgo": "bajo",
                                        "alertas": [],
                                        "resumen": "Analizando..."
                                    },
                                    "progressive": True
                                })

                        # Control de cierre
                        elif data.get("type") in ["close", "end", "finish"] or message.get("text", "").lower() in ["close", "end", "finish"]:
                            logger.info(f"Cierre solicitado por cliente")
                            break
                    except json.JSONDecodeError:
                        # Si no es JSON válido, tratar como mensaje de cierre
                        msg_text = message.get("text", "").lower()
                        if msg_text in ["close", "end", "finish"]:
                            logger.info(f"Cierre solicitado por cliente")
                            break

            except asyncio.TimeoutError:
                logger.info(f"⏱️ Timeout esperando datos")
                break
            except Exception as e:
                logger.debug(f"Error recibiendo: {e}")
                break

    except Exception as e:
        logger.error(f"❌ Error WebSocket: {e}")
    finally:
        # Limpiar
        if ws_id in active_connections:
            del active_connections[ws_id]
        logger.info(f"🌐 Cliente desconectado: {ws_id}")


@app.websocket("/ws/transcript")
async def websocket_transcript(websocket: WebSocket):
    """WebSocket legacy para compatibilidad - NO USADO EN NUEVO FLUJO"""
    await websocket.accept()

    # Generar ID único para esta sesión
    ws_id = str(uuid.uuid4())
    active_connections[ws_id] = websocket

    logger.info(f"🌐 Cliente conectado (legacy): {ws_id}")

    try:
        # Enviar ID al cliente
        await websocket.send_json({
            "type": "ws_id",
            "id": ws_id
        })

        logger.info(f"📤 WebSocket ID enviado: {ws_id}")

        # Mantener la conexión abierta
        while True:
            try:
                # Esperar mensajes de keep-alive
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=300.0  # 5 minutos
                )
                logger.debug(f"Mensaje de {ws_id}: {data[:50]}")
            except asyncio.TimeoutError:
                logger.info(f"Timeout en {ws_id}, cerrando...")
                break
            except Exception as e:
                logger.debug(f"Conexión cerrada: {e}")
                break

    except Exception as e:
        logger.error(f"❌ Error WebSocket: {e}")
    finally:
        # Limpiar
        if ws_id in active_connections:
            del active_connections[ws_id]
        logger.info(f"🌐 Cliente desconectado: {ws_id}")


@app.on_event("startup")
async def startup():
    """Inicia el servidor"""
    logger.info("🚀 Iniciando Copiloto Médico v6.3.1 (AssemblyAI + Análisis IA Progresivo)")
    logger.info(f"✅ Servidor listo en http://{HOST}:{PORT}")

    if ASSEMBLYAI_API_KEY:
        logger.info("📌 AssemblyAI: ✅ Configurado")
        logger.info("🎯 Modo: Batch Processing (archivo completo)")
        logger.info("📊 Diarización: ✅ Integrada en AssemblyAI (speaker_labels)")
    else:
        logger.error("❌ ASSEMBLYAI_API_KEY no configurada")
        logger.error("❌ Transcripción no disponible sin AssemblyAI")

    # Análisis IA - Mostrar prioridad disponible
    if ANTHROPIC_API_KEY:
        logger.info("🤖 Análisis IA: ✅ Claude (Anthropic) - PRIORIDAD 1")
    # elif GEMINI_API_KEY:
    #     logger.info("🤖 Análisis IA: ✅ Gemini (Google) - PRIORIDAD 2")
    if OPENAI_API_KEY:
        logger.info("🤖 Análisis IA: ✅ OpenAI (GPT-3.5) - PRIORIDAD 2")
    logger.info("🤖 Análisis IA: ✅ Ollama (llama3.2) - FALLBACK LOCAL")
    logger.info("📝 Análisis automático: ✅ Preguntas, riesgo, alertas")

    # DEEPGRAM - DESACTIVADO TEMPORALMENTE
    # if DEEPGRAM_API_KEY:
    #     logger.info(f"🎤 Deepgram: ✅ Configurado ({DEEPGRAM_MODEL})")

    try:
        from pydub.utils import mediainfo
        logger.info("✅ pydub: ✅ Disponible")
    except:
        logger.warning("⚠️  pydub: ❌ No disponible (instala: pip install pydub)")


@app.on_event("shutdown")
async def shutdown():
    """Detiene el servidor"""
    logger.info("🛑 Deteniendo servidor...")
    logger.info("✅ Servidor detenido")


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Iniciando servidor en {HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT, log_level=LOG_LEVEL.lower())
