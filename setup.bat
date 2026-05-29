@echo off
REM Script de instalación para Copiloto Médico v2.0 en Windows

setlocal enabledelayedexpansion

echo.
echo ============================================
echo   Copiloto Médico v2.0 - Setup (Windows)
echo ============================================
echo.

REM Verificar que Python está instalado
echo [PREP] Verificando Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Python no está instalado o no está en el PATH
    echo Descarga desde: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version') do echo ✓ %%i
echo.

REM Paso 1: Crear entorno virtual
echo ============================================
echo [1/5] Creando entorno virtual...
echo ============================================
python -m venv venv
if %errorlevel% neq 0 (
    echo.
    echo ERROR: No se pudo crear el entorno virtual
    echo.
    pause
    exit /b 1
)
echo ✓ Entorno virtual creado
echo.

REM Paso 2: Activar entorno virtual
echo ============================================
echo [2/5] Activando entorno virtual...
echo ============================================
call venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo.
    echo ERROR: No se pudo activar el entorno virtual
    echo.
    pause
    exit /b 1
)
echo ✓ Entorno virtual activado
echo.

REM Paso 3: Actualizar herramientas fundamentales
echo ============================================
echo [3/5] Actualizando pip, setuptools y wheel...
echo ============================================
pip install --upgrade pip setuptools wheel
if %errorlevel% neq 0 (
    echo.
    echo ERROR: No se pudieron actualizar las herramientas
    echo.
    pause
    exit /b 1
)
echo ✓ pip, setuptools y wheel actualizados
echo.

REM Paso 4: Instalar dependencias
echo ============================================
echo [4/5] Instalando dependencias del proyecto...
echo ============================================
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo ERROR: No se pudieron instalar las dependencias
    echo.
    pause
    exit /b 1
)
echo ✓ Todas las dependencias instaladas
echo.

REM Paso 5: Configuración
echo ============================================
echo [5/5] Configurando proyecto...
echo ============================================
if not exist .env (
    copy .env.example .env
    echo ✓ Archivo .env creado
) else (
    echo ✓ Archivo .env ya existe
)
echo.

REM Verificación final
echo ============================================
echo   Setup completado correctamente!
echo ============================================
echo.
echo Próximos pasos:
echo.
echo 1. Configura las API Keys en .env:
echo    - DAILY_API_KEY (desde https://dashboard.daily.co)
echo    - DAILY_ROOM_URL (tu sala de Daily.co)
echo    - DEEPGRAM_API_KEY (desde https://console.deepgram.com)
echo.
echo 2. Inicia el servidor:
echo    python main.py
echo.
echo 3. Accede en el navegador:
echo    http://localhost:8000
echo.
echo Documentación: Abre el archivo README.md
echo.
pause
