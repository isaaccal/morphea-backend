# agents/freud_agent.py

"""
Agente Freud con RAG manual:
1. Busca en pgvector los 3 mejores fragmentos.
2. Construye el prompt con dream, context y language.
3. Llama a ChatOpenAI y devuelve la interpretación.
"""

import os
import pathlib
from typing import Dict, List

from dotenv import load_dotenv
load_dotenv()

import openai
from pypdf import PdfReader

# LangChain imports
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores import PGVector
from langchain_community.chat_models import ChatOpenAI
from langchain.schema import Document, HumanMessage

# ---------- Configuración RAG ----------
# Ruta al PDF (no se usa aquí, porque ya ingresaste)
# PDF_PATH = pathlib.Path("data/freud_interpretation_of_dreams.pdf")

# Clave OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Conexión a tu DB con vector store
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")
if not SQLALCHEMY_DATABASE_URL:
    raise ValueError("Falta DATABASE_URL en el .env")

# Inicializa embeddings y vector store
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
vector_store = PGVector(
    collection_name="freud_dreams",
    connection_string=SQLALCHEMY_DATABASE_URL,
    embedding_function=embeddings,
)

# Prompt maestro
PROMPT_TMPL = """Eres Sigmund Freud y explicas sueños con referencias exactas a tu obra.

<SUEÑO>
{dream}
</SUEÑO>

Usa el contexto (fragmentos originales) para fundamentar tu respuesta.
Responde en {language}. Cita fuente entre paréntesis: (Freud, 1900, p.<número>).

CONTEXTO:
{context}
"""

def interpret_freud(dream_text: str, language: str = "es") -> Dict:
    # 1. Recuperar documentos
    retriever = vector_store.as_retriever(search_kwargs={"k": 3})
    docs: List[Document] = retriever.get_relevant_documents(dream_text)

    # 2. Construir contexto
    context = "\n\n".join([doc.page_content for doc in docs])

    # 3. Formatear prompt
    prompt_str = PROMPT_TMPL.format(
        dream=dream_text,
        context=context,
        language=language
    )

    # 4. Llamar a LLM
    llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.7)
    response = llm.chat([HumanMessage(content=prompt_str)])
    interpretation = response.content.strip()

    # 5. Devolver formato esperado
    return {
        "agent": "freud",
        "timestamp": response.additional_kwargs.get("created_at") 
                    if hasattr(response, "additional_kwargs") else None,
        "text": interpretation,
    }
