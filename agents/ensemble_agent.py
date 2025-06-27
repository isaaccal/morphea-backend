# agents/ensemble_agent.py

import os
from dotenv import load_dotenv
load_dotenv()

from typing import Dict, List
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores import PGVector
from langchain_openai.chat_models import ChatOpenAI
from langchain.schema import Document, HumanMessage

# --- Configuración de Vector Stores para cada autor ---
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("Falta DATABASE_URL en el .env")

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

def make_retriever(collection_name: str):
    store = PGVector(
        collection_name=collection_name,
        connection_string=DATABASE_URL,
        embedding_function=embeddings,
    )
    return store.as_retriever(search_kwargs={"k": 2})

retrievers = {
    "Freud": make_retriever("freud_dreams"),
    "Jung":  make_retriever("jung_dreams"),
    "Adler": make_retriever("adler_dreams"),
}

# --- Plantilla de prompt para el ensemble ---
ENSPROMPT = """
Interpreta este sueño integrando teorías de psicología profunda:

Conceptos freudianos:
{ctx_freud}

Conceptos junguianos:
{ctx_jung}

Conceptos adlerianos:
{ctx_adler}

Sueño del usuario:
\"\"\"
{dream}
\"\"\"

Por favor, responde en tercera persona, de forma clara y unificada, 
usando las ideas de cada autor sin citar páginas ni fingir ser ellos.
"""

def interpret_ensemble(dream_text: str, language: str = "es") -> Dict:
    # 1) Recuperar los fragmentos más relevantes de cada colección
    contexts: Dict[str, str] = {}
    for author, retriever in retrievers.items():
        docs: List[Document] = retriever.get_relevant_documents(dream_text)
        contexts[author] = "\n\n".join(d.page_content for d in docs)

    # 2) Formatear el prompt
    prompt = ENSPROMPT.format(
        ctx_freud=contexts["Freud"],
        ctx_jung=contexts["Jung"],
        ctx_adler=contexts["Adler"],
        dream=dream_text
    )

    # 3) Llamar al LLM
    llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.7)
    response = llm.chat([HumanMessage(content=prompt)])
    interpretation = response.content.strip()

    # 4) Devolver el formato estándar
    return {
        "agent": "ensemble",
        "timestamp": None,
        "text": interpretation,
    }
