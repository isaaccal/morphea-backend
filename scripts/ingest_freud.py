# scripts/ingest_freud.py

"""
Convierte el PDF 'freud_interpretation_of_dreams.pdf' a texto,
genera embeddings y los guarda en Postgres (pgvector).

Ejecútalo una sola vez:
    python scripts/ingest_freud.py
"""

import os
import pathlib
from typing import List

# 1) Cargar variables de .env
from dotenv import load_dotenv
load_dotenv()

# 2) Importaciones para RAG
import openai
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import PGVector
from pypdf import PdfReader

# ---------- 1. Configuración ----------
PDF_PATH = pathlib.Path("data/freud_interpretation_of_dreams.pdf")

# Clave OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# URL SQLAlchemy (debe venir en tu .env)
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")
if not SQLALCHEMY_DATABASE_URL:
    raise ValueError("No se encontró DATABASE_URL en tu .env")

COLLECTION_NAME = "freud_dreams"
CHUNK_SIZE = 1_000   # caracteres aprox.
CHUNK_OVERLAP = 200

# ---------- 2. Leer PDF ----------
reader = PdfReader(PDF_PATH)
raw_text = "\n".join(page.extract_text() or "" for page in reader.pages)

# ---------- 3. Trocear ----------
splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", ".", " ", ""],
    length_function=len,
)
docs: List[str] = splitter.split_text(raw_text)
print(f"Trozos creados: {len(docs)}")

# ---------- 4. Generar embeddings y guardar en pgvector ----------
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
store = PGVector(
    collection_name=COLLECTION_NAME,
    connection_string=SQLALCHEMY_DATABASE_URL,
    embedding_function=embeddings,
)
store.add_texts(docs)
print("¡Embeddings guardados en Postgres con pgvector!")
