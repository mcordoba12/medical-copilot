# Copiloto Médico - Transcripción de Audio con Diarización

Sistema de transcripción y diarización de llamadas médicas usando **AssemblyAI** para procesar audio completo con identificación automática de speaker (Paciente/Doctor).

**Versión:** 6.2.0
**Tipo de procesamiento:** Batch (análisis completo antes de reproducción)
**Resultado:** Transcripción perfectamente sincronizada con subtítulos

---

## REQUISITOS DEL SISTEMA

**OBLIGATORIO:**
- **Python 3.11** (no 3.12, no 3.13 - versión exacta)
- **Anaconda** instalado (https://www.anaconda.com/download)
- **Windows 10/11** (64-bit)
- **~500 MB** de espacio en disco
- **Conexión a internet** (para APIs de AssemblyAI)

**Hardware mínimo:**
- Procesador: 2 GHz dual-core
- RAM: 4 GB
- Navegador moderno (Chrome, Firefox, Edge, Safari)

---

## INSTALACIÓN PASO A PASO

### Paso 1: Abrir Anaconda Prompt

1. Presiona **Windows + R**
2. Escribe: `anaconda prompt`
3. Presiona Enter

Deberías ver una ventana negra que dice `(base)` al principio de cada línea.

### Paso 2: Navegar a la carpeta del proyecto

```bash
cd "C:\Users\TuUsuario\Documents\8 Octavo Semestre\IA 2\Proyecto coomeva\medical-copilot"
```

*(Reemplaza "TuUsuario" con tu nombre de usuario de Windows)*

Verifica que estás en la carpeta correcta:
```bash
dir
```

Deberías ver archivos como `main.py`, `index.html`, `config.py`, etc.

### Paso 3: Crear ambiente conda con Python 3.11

```bash
conda create -n medical-copilot python=3.11 -y
```

*(Toma ~2-3 minutos)*

### Paso 4: Activar el ambiente

```bash
conda activate medical-copilot
```

Ahora el prompt debería mostrar `(medical-copilot)` en lugar de `(base)`.

### Paso 5: Instalar dependencias

```bash
pip install fastapi uvicorn websockets httpx python-dotenv pydub
```

*(Toma ~1-2 minutos)*

### Paso 6: Instalar FFmpeg

**Opción A: Con conda (RECOMENDADO):**
```bash
conda install ffmpeg -y
```

**Opción B: Manual**
1. Ve a https://ffmpeg.org/download.html
2. Descarga versión Windows
3. Extrae en `C:\ffmpeg\`
4. Agrega `C:\ffmpeg\bin` a variables de entorno de Windows

### Paso 7: Verificar instalación

```bash
python --version
pip list
```

Deberías ver Python 3.11.x y fastapi, uvicorn, etc. en la lista.

---

## API KEYS NECESARIAS

### AssemblyAI (OBLIGATORIO)

**Obtener API Key:**
1. Ve a https://www.assemblyai.com/
2. Clic en "Get Started"
3. Registrate con email
4. Confirma tu email
5. Ingresa al dashboard
6. Busca "API Token"
7. Copia tu API key

**Costo:**
- Plan Free: $0 (3 horas/mes)
- Después: $0.10 por minuto de audio

---

## CONFIGURACIÓN DEL ARCHIVO .env

### Crear el archivo .env

En la carpeta del proyecto, crea un archivo `.env` (sin extensión):

1. Abre Notepad
2. Copia esto:

```
ASSEMBLYAI_API_KEY=tu_api_key_aqui
HOST=127.0.0.1
PORT=8000
LOG_LEVEL=INFO
```

3. Guarda como `.env`
   - En Notepad: File → Save As
   - Nombre: `.env`
   - Tipo: "All files (*.*)"

### Agregar tu API Key

Reemplaza `tu_api_key_aqui` con tu verdadera API Key:

```
ASSEMBLYAI_API_KEY=abc123def456ghi789jkl
```

Verifica:
```bash
type .env
```

---

## CÓMO CORRER EL PROYECTO

### Desde Anaconda Prompt

```bash
cd "C:\Users\TuUsuario\Documents\8 Octavo Semestre\IA 2\Proyecto coomeva\medical-copilot"
conda activate medical-copilot
python main.py
```

Deberías ver:
```
🚀 Iniciando Copiloto Médico v6.2.0 (AssemblyAI - Batch Processing)
✅ Servidor listo en http://127.0.0.1:8000
```

### Crear archivo batch (doble clic para ejecutar)

1. Abre Notepad
2. Copia esto:

```batch
@echo off
cd "C:\Users\TuUsuario\Documents\8 Octavo Semestre\IA 2\Proyecto coomeva\medical-copilot"
call conda activate medical-copilot
python main.py
pause
```

3. Guarda como `correr_servidor.bat`

### Abrir en navegador

Abre: http://127.0.0.1:8000

### Detener servidor

Presiona: **Ctrl + C** en Anaconda Prompt

---

## CÓMO USAR EL SISTEMA

### Flujo:

1. **Cargar archivo**
   - Haz clic en "📁 Seleccionar"
   - Elige un archivo de audio (MP3, WAV, M4A, etc.)

2. **Esperar análisis**
   - Verás: "⏳ Analizando audio con AssemblyAI..."
   - El Play está grisado
   - Espera 15-30 segundos

3. **Análisis completado**
   - Verás: "✅ Análisis completado"
   - Play se habilita
   - Se muestran los utterances

4. **Reproducir**
   - Presiona Play
   - Audio se reproduce con subtítulos sincronizados
   - Verde = Paciente
   - Azul = Doctor

5. **Controles**
   - Pausa
   - Reanuda
   - Arrastra para saltar
   - Intercambiar speakers

---

## SOLUCIÓN DE PROBLEMAS

### "Python 3.11 not found"
```bash
conda remove python -y
conda create -n medical-copilot python=3.11 -y
conda activate medical-copilot
```

### "ModuleNotFoundError: No module named 'fastapi'"
```bash
conda activate medical-copilot
pip install fastapi uvicorn websockets httpx python-dotenv pydub
```

### "ASSEMBLYAI_API_KEY not configured"
1. Verifica que existe `.env` en la carpeta
2. Contiene: `ASSEMBLYAI_API_KEY=tu_clave`
3. Reinicia: `python main.py`

### "Error processing audio: NotSupportedError"
- Convierte a MP3 o WAV
- Usa navegador moderno (Chrome, Firefox, Edge)

### "ffmpeg not found"
```bash
conda activate medical-copilot
conda install ffmpeg -y
```

### WebSocket error
1. Abre consola: F12 → Console
2. Recarga: F5
3. Deberías ver: "WebSocket de streaming abierto"
4. Si no, reinicia servidor

### "Analizando..." no termina
1. Espera 30-60 segundos
2. Recarga página: F5
3. Verifica API key en AssemblyAI Dashboard
4. Actualiza `.env` y reinicia

### "Cannot read property 'arrayBuffer' of null"
1. Carga archivo diferente
2. Verifica que no está corrupto
3. Intenta con MP3 pequeño

---

## ESTRUCTURA

```
medical-copilot/
├── main.py              # Servidor backend
├── config.py            # Configuración
├── index.html           # Interfaz web
├── .env                 # API keys
└── README.md            # Este archivo
```

---

## SEGURIDAD

- Nunca compartas tu API key
- Nunca subas `.env` a GitHub
- `.gitignore`:

```
.env
__pycache__/
*.pyc
```

---

## SOPORTE

1. Consola navegador (F12 → Console)
2. Logs del servidor (ventana Anaconda)
3. Verifica API Key en AssemblyAI
4. Reinicia: cierra y abre nuevamente

---

## CRÉDITOS

- Backend: FastAPI, WebSockets
- Frontend: HTML5, JavaScript
- Transcripción: AssemblyAI
- Diarización: AssemblyAI

---

## LICENCIA

Proyecto educativo - Uso libre para propósitos académicos.
