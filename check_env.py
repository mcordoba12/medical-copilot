import os
from dotenv import load_dotenv
load_dotenv()
key = os.getenv('DEEPGRAM_API_KEY', 'NO ENCONTRADA')
print(f'Key cargada: {key[:8]}...')
print(f'Longitud: {len(key)} caracteres')