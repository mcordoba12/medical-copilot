import os
from dotenv import load_dotenv

load_dotenv()

# Servidor
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", 8000))

# Deepgram
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
DEEPGRAM_LANGUAGE = os.getenv("DEEPGRAM_LANGUAGE", "es")
DEEPGRAM_MODEL = os.getenv("DEEPGRAM_MODEL", "nova-2")
DEEPGRAM_PUNCTUATE = os.getenv("DEEPGRAM_PUNCTUATE", "true")
DEEPGRAM_INTERIM_RESULTS = os.getenv("DEEPGRAM_INTERIM_RESULTS", "true")

# AssemblyAI
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY", "")

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
