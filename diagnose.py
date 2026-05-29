#!/usr/bin/env python
"""Diagnóstico del sistema Copiloto Médico v5.0"""

import sys
import asyncio
import json

print("=" * 60)
print("DIAGNOSTICO: Copiloto Medico v5.0")
print("=" * 60)

# 1. Verificar imports
print("\n1. Verificando imports...")
try:
    import fastapi
    print("   OK fastapi")
except ImportError as e:
    print(f"   ERROR fastapi: {e}")
    sys.exit(1)

try:
    import websockets
    print("   OK websockets")
except ImportError as e:
    print(f"   ERROR websockets: {e}")
    sys.exit(1)

try:
    from pydub import AudioSegment
    print("   OK pydub")
except ImportError as e:
    print(f"   WARNING pydub: {e}")
    print("   Instala: pip install pydub")

try:
    import uvicorn
    print("   OK uvicorn")
except ImportError as e:
    print(f"   ERROR uvicorn: {e}")
    sys.exit(1)

# 2. Verificar config
print("\n2. Verificando config...")
try:
    from config import HOST, PORT, DEEPGRAM_API_KEY, DEEPGRAM_MODEL
    print(f"   HOST: {HOST}")
    print(f"   PORT: {PORT}")
    print(f"   DEEPGRAM_MODEL: {DEEPGRAM_MODEL}")

    if DEEPGRAM_API_KEY:
        print(f"   DEEPGRAM_API_KEY: {DEEPGRAM_API_KEY[:8]}...")
    else:
        print("   ERROR: DEEPGRAM_API_KEY no configurada en .env")
        sys.exit(1)
except Exception as e:
    print(f"   ERROR config: {e}")
    sys.exit(1)

# 3. Verificar archivos
print("\n3. Verificando archivos...")
import os

for file in ['main.py', 'index.html', 'config.py']:
    if os.path.exists(file):
        size = os.path.getsize(file)
        print(f"   OK {file} ({size} bytes)")
    else:
        print(f"   ERROR {file} no encontrado")
        sys.exit(1)

# 4. Probar compilacion
print("\n4. Compilando Python...")
try:
    import py_compile
    py_compile.compile('main.py', doraise=True)
    print("   OK main.py compila")
except Exception as e:
    print(f"   ERROR: {e}")
    sys.exit(1)

# 5. Probar WebSocket
print("\n5. Probando WebSocket...")
print(f"   URL: ws://{HOST}:{PORT}/ws/transcript")
print("   ")
print("   PASOS:")
print("   1. Abre http://localhost:8000 en el navegador")
print("   2. Abre la consola (F12)")
print("   3. Deberias ver: 'WebSocket ID recibido: ...'")
print("   ")
print("   Si NO ves eso:")
print("   a) Verifica que el servidor esta corriendo (python main.py)")
print("   b) Revisa errores en la consola del navegador (F12)")
print("   c) Revisa logs del servidor")

# 6. Resumen
print("\n" + "=" * 60)
print("DIAGNOSTICO COMPLETADO")
print("=" * 60)
print("\nPara iniciar el servidor:")
print("  python main.py")
print("\nLuego abre:")
print(f"  http://{HOST}:{PORT}")
print("\nSi no conecta, revisa:")
print("  1. F12 -> Console en el navegador")
print("  2. Logs del servidor (python main.py)")
print("  3. Que el puerto 8000 no este en uso")
