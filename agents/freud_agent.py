
# agents/freud_agent.py

"""
Agente Freud con RAG manual corregido:
1. Busca en pgvector los 3 mejores fragmentos.
2. Construye el prompt con dream, context y language.
3. Llama a ChatOpenAI usando generate() y devuelve la interpretación.
"""

import os
from dotenv import load_dotenv
load_dotenv()

from typing import Dict, List
from pypdf import PdfReader

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores import PGVector
from langchain_openai.chat_models import ChatOpenAI  # ojo al import
from langchain.schema import Document, HumanMessage

# --- Configuración RAG ---
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise ValueError("Falta OPENAI_API_KEY en el .env")

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")
if not SQLALCHEMY_DATABASE_URL:
    raise ValueError("Falta DATABASE_URL en el .env")

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
vector_store = PGVector(
    collection_name="freud_dreams",
    connection_string=SQLALCHEMY_DATABASE_URL,
    embedding_function=embeddings
)

PROMPT_TMPL = """Eres Sigmund Freud y explicas sueños con referencias exactas a tu obra.

<SUEÑO>
{dream}
</SUEÑO>

Usa el contexto (fragmentos originales) para fundamentar tu respuesta.
Responde en {language}. Cita fuente entre paréntesis: (Freud, 1900, p.<número>).

CONTEXTO:
{context}
"""

def freud_interpretation(dream_text: str, language: str = "es") -> Dict:
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

    # 4. Llamar a LLM usando el API generate()
    llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.7)
    # `generate` espera una lista de listas de mensajes
    chat_input = [HumanMessage(content=prompt_str)]
    result = llm.generate([chat_input])

    # 5. Extraer contenido de la primera generación
    interpretation = result.generations[0][0].message.content.strip()

    # 6. Devolver formato esperado
    return {
        "agent": "freud",
        "timestamp": result.generations[0][0].generation_info.get("created_at"),
        "text": interpretation,
    }
