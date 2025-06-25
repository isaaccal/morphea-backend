# agents/freud_agent.py

"""
Agente RAG de Freud para Morphea.ai:
Recupera fragmentos del PDF ingestado y genera interpretaciones con citas exactas.
"""

import os
from datetime import datetime
from dotenv import load_dotenv

# Cargar variables de entorno (.env)
load_dotenv()

import openai
from langchain.chat_models import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.chains import RetrievalQA
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores import PGVector

# Configuración de OpenAI
environment_key = os.getenv("OPENAI_API_KEY")
if not environment_key:
    raise ValueError("Falta la variable OPENAI_API_KEY en el entorno")
openai.api_key = environment_key

# Conexión RAG: usar DATABASE_URL de .env para pgvector
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")
if not SQLALCHEMY_DATABASE_URL:
    raise ValueError("Falta DATABASE_URL en el entorno para RAG de Freud")

COLLECTION_NAME = "freud_dreams"

# Crear instancia de embeddings y vectorstore
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
vector_store = PGVector(
    collection_name=COLLECTION_NAME,
    connection_string=SQLALCHEMY_DATABASE_URL,
    embedding_function=embeddings,
)

# Prompt maestro con contexto RAG
template = """
Eres Sigmund Freud y explicas sueños con referencias exactas a tu obra.

<SUEÑO>
{dream}
</SUEÑO>

Usa los fragmentos a continuación (CONTEXTO) para fundamentar tu respuesta.
Responde en {language}. Cita fuente entre paréntesis: (Freud, 1900, p.<número>).

CONTEXTO:
{context}
"""
prompt = PromptTemplate(
    input_variables=["dream", "context", "language"],
    template=template,
)

# Cadena RetrievalQA
qa_chain = RetrievalQA.from_chain_type(
    llm=ChatOpenAI(model_name="gpt-4o-mini", temperature=0.7),
    chain_type="stuff",
    retriever=vector_store.as_retriever(search_kwargs={"k": 3}),
    chain_type_kwargs={"prompt": prompt},
)

def interpret_freud(dream_text: str, language: str = "es") -> dict:
    """
    Genera una interpretación de Freud usando RAG.
    Retorna un dict con campos:
      - agent: 'freud'
      - timestamp: ISO UTC
      - text: la interpretación completa
    """
    result = qa_chain({"query": dream_text, "language": language})
    interpretation = result["result"].strip()
    return {
        "agent": "freud",
        "timestamp": datetime.utcnow().isoformat(),
        "text": interpretation,
    }
