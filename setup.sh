#!/bin/bash

# Script de instalación para Copiloto Médico v2.0 en Linux/Mac

echo ""
echo "============================================"
echo "  Copiloto Médico v2.0 - Setup (Linux/Mac)"
echo "============================================"
echo ""

# Verificar que Python está instalado
echo "[PREP] Verificando Python..."
if ! command -v python3 &> /dev/null; then
    echo ""
    echo "ERROR: Python3 no está instalado"
    echo "Instala desde: https://www.python.org/downloads/"
    echo ""
    exit 1
fi
python3 --version
echo "✓ Python encontrado"
echo ""

# Paso 1: Crear entorno virtual
echo "============================================"
echo "[1/5] Creando entorno virtual..."
echo "============================================"
python3 -m venv venv || { echo "ERROR: No se pudo crear el entorno virtual"; exit 1; }
echo "✓ Entorno virtual creado"
echo ""

# Paso 2: Activar entorno virtual
echo "============================================"
echo "[2/5] Activando entorno virtual..."
echo "============================================"
source venv/bin/activate || { echo "ERROR: No se pudo activar el entorno virtual"; exit 1; }
echo "✓ Entorno virtual activado"
echo ""

# Paso 3: Actualizar herramientas fundamentales
echo "============================================"
echo "[3/5] Actualizando pip, setuptools y wheel..."
echo "============================================"
pip install --upgrade pip setuptools wheel || { echo "ERROR: No se pudieron actualizar las herramientas"; exit 1; }
echo "✓ pip, setuptools y wheel actualizados"
echo ""

# Paso 4: Instalar dependencias
echo "============================================"
echo "[4/5] Instalando dependencias del proyecto..."
echo "============================================"
pip install -r requirements.txt || { echo "ERROR: No se pudieron instalar las dependencias"; exit 1; }
echo "✓ Todas las dependencias instaladas"
echo ""

# Paso 5: Configuración
echo "============================================"
echo "[5/5] Configurando proyecto..."
echo "============================================"
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✓ Archivo .env creado"
else
    echo "✓ Archivo .env ya existe"
fi
echo ""

# Verificación final
echo "============================================"
echo "  Setup completado correctamente!"
echo "============================================"
echo ""
echo "Próximos pasos:"
echo ""
echo "1. Configura las API Keys en .env:"
echo "   - DAILY_API_KEY (desde https://dashboard.daily.co)"
echo "   - DAILY_ROOM_URL (tu sala de Daily.co)"
echo "   - DEEPGRAM_API_KEY (desde https://console.deepgram.com)"
echo ""
echo "2. Inicia el servidor:"
echo "   python main.py"
echo ""
echo "3. Accede en el navegador:"
echo "   http://localhost:8000"
echo ""
echo "Documentación: Abre el archivo README.md"
echo ""
