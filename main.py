import asyncio
import json
import logging
import io
import os
import uuid
import tempfile
import httpx
import traceback
from datetime import datetime
from fastapi import FastAPI, WebSocket, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import websockets
from pydub import AudioSegment
from pydub.utils import mediainfo
from config import (
    HOST, PORT, LOG_LEVEL,
    DEEPGRAM_API_KEY,
    DEEPGRAM_LANGUAGE, DEEPGRAM_MODEL, DEEPGRAM_PUNCTUATE,
    ASSEMBLYAI_API_KEY,
)

logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Copiloto Médico", version="5.1.0")

# Conexiones WebSocket activas: { websocket_id: WebSocket }
active_connections = {}

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

                    # Procesar y enviar utterances
                    for i, utt in enumerate(utterances):
                        # Convertir speaker label (A, B, etc.) a número (0, 1, etc.)
                        speaker = ord(utt.get("speaker", "A")) - ord("A")
                        text = utt.get("text", "").strip()

                        if text and client_ws:
                            # Solo marcar como final el último utterance
                            is_final = (i == len(utterances) - 1)
                            await client_ws.send_json({
                                "type": "transcription",
                                "text": text,
                                "speaker": speaker,
                                "start": utt.get("start", 0) / 1000,  # Convertir ms a segundos
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
    logger.info("🚀 Iniciando Copiloto Médico v6.2.0 (AssemblyAI - Batch Processing)")
    logger.info(f"✅ Servidor listo en http://{HOST}:{PORT}")

    if ASSEMBLYAI_API_KEY:
        logger.info("📌 AssemblyAI: ✅ Configurado")
        logger.info("🎯 Modo: Batch Processing (archivo completo)")
        logger.info("📊 Diarización: ✅ Integrada en AssemblyAI (speaker_labels)")
    else:
        logger.error("❌ ASSEMBLYAI_API_KEY no configurada")
        logger.error("❌ Transcripción no disponible sin AssemblyAI")

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
