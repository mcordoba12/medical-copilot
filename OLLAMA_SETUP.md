# Instalación de Ollama y Configuración de llama3.2

## ¿Qué es Ollama?

Ollama es una herramienta que permite ejecutar modelos de lenguaje grandes (LLM) localmente en tu computadora sin necesidad de conexión a internet o APIs de terceros.

En el Copiloto Médico, usamos **llama3.2** para análisis automático de transcripciones.

---

## Instalación de Ollama

### Paso 1: Descargar Ollama

1. Ve a https://ollama.ai
2. Haz clic en "Download"
3. Descarga la versión para **Windows**
4. Ejecuta el instalador (`.exe`)
5. Sigue los pasos del instalador

**Requisitos mínimos:**
- Windows 10/11
- 8 GB de RAM (mínimo)
- 8 GB de espacio en disco (para llama3.2)
- GPU NVIDIA o AMD (opcional pero recomendado)

### Paso 2: Verificar instalación

Abre una terminal (Anaconda Prompt o CMD) y ejecuta:

```bash
ollama --version
```

Deberías ver algo como: `ollama version 0.1.x`

---

## Descargar el modelo llama3.2

### Desde Anaconda Prompt

```bash
ollama pull llama3.2
```

Esto descargará el modelo (~5 GB). **Toma ~10-20 minutos** dependiendo de tu conexión.

**Verás algo como:**
```
pulling manifest
pulling 8934d386d91e
pulling de7fe7f21b0a
pulling 8c5e3ba64179
pulling f017f3e842ff
pulling e5d18e05415b
pulling eb6f86b1b692
verifying sha256 digest
writing manifest
success
```

### Verificar que el modelo está descargado

```bash
ollama list
```

Deberías ver `llama3.2` en la lista.

---

## Ejecutar Ollama (modo servidor)

Ollama corre como un servicio en background en el puerto **11434**.

### Opción 1: Ollama se inicia automáticamente

Si instalaste Ollama correctamente, debería iniciarse automáticamente al reiniciar tu computadora.

Para verificar:
```bash
curl http://localhost:11434/api/tags
```

Deberías ver una respuesta con tu modelo.

### Opción 2: Iniciar manualmente

Si no está corriendo, abre Anaconda Prompt y ejecuta:

```bash
ollama serve
```

Verás:
```
2024/01/15 10:30:45 "POST /api/chat HTTP/1.1" 200 856
2024/01/15 10:30:46 "POST /api/chat HTTP/1.1" 200 1234
```

**Deja esta ventana abierta mientras usas el Copiloto Médico.**

---

## Prueba rápida de Ollama

En otra terminal, ejecuta:

```bash
ollama run llama3.2 "Hola, ¿cómo estás?"
```

Deberías ver una respuesta del modelo (toma ~5-10 segundos la primera vez).

---

## Integración con el Copiloto Médico

Una vez que Ollama esté corriendo:

1. Inicia el servidor del Copiloto:
   ```bash
   conda activate medical-copilot
   python main.py
   ```

2. Abre http://127.0.0.1:8000

3. Carga un audio y transcribe normalmente

4. Cuando AssemblyAI complete la transcripción, **automáticamente se enviará a Ollama** para análisis

5. Verás el análisis en un panel lateral con:
   - Preguntas sugeridas
   - Datos del paciente detectados
   - Nivel de riesgo
   - Alertas
   - Resumen de la llamada

---

## Troubleshooting

### "Failed to connect to localhost:11434"

**Problema:** Ollama no está corriendo.

**Solución:**
1. Abre otra terminal
2. Ejecuta: `ollama serve`
3. Deja la ventana abierta

### "Model not found"

**Problema:** llama3.2 no está descargado.

**Solución:**
```bash
ollama pull llama3.2
```

### "Out of memory"

**Problema:** Tu computadora no tiene suficiente RAM.

**Solución:**
- Instalar un modelo más pequeño:
  ```bash
  ollama pull phi
  ```
- O aumentar RAM disponible cerrando otras aplicaciones

### Análisis toma mucho tiempo

**Problema:** Ollama es lento (normal en computadoras sin GPU).

**Solución:**
- Primera ejecución de un modelo toma más tiempo
- Próximas ejecuciones serán más rápidas
- Si tienes GPU NVIDIA, Ollama la usará automáticamente

### GPU no se detecta

**Problema:** Ollama usa CPU en lugar de GPU.

**Solución:**
1. Instala NVIDIA CUDA Toolkit
2. Reinstala Ollama
3. Verifica: `ollama ps` (debe mostrar GPU)

---

## Modelos alternativos

Si llama3.2 es muy pesado, puedes usar:

```bash
ollama pull phi
ollama pull mistral
ollama pull neural-chat
```

**Tamaños:**
- `phi`: 2.7 GB (rápido, menos preciso)
- `neural-chat`: 4.1 GB (equilibrado)
- `mistral`: 4.1 GB (preciso)
- `llama3.2`: 5.4 GB (recomendado)

Para cambiar el modelo en `main.py`, busca:
```python
response = await asyncio.to_thread(
    ollama.chat,
    model="llama3.2",  # <-- Cambiar aquí
```

---

## Desactivar Ollama (si no lo necesitas)

Si quieres que el Copiloto funcione sin análisis IA:

En `main.py`, comenta la función `analyze_with_ollama()`:

```python
# if full_transcript and client_ws:
#     analysis = await analyze_with_ollama(full_transcript)
```

---

## Recursos adicionales

- Ollama oficial: https://ollama.ai
- Modelos disponibles: https://ollama.ai/library
- Documentación: https://github.com/ollama/ollama

---

**¿Necesitas ayuda?** Revisa los logs en la consola del servidor o la terminal de Ollama.
