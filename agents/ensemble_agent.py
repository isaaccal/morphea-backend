# agents/ensemble_agent.py

import os
from dotenv import load_dotenv
load_dotenv()

from typing import Dict, List
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores import PGVector
from langchain_openai.chat_models import ChatOpenAI
from langchain.schema import Document, HumanMessage

# —–––– Configuración de RAG para cada escuelas –––––—
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

retrievers = [
    make_retriever("freud_dreams"),
    make_retriever("jung_dreams"),
    make_retriever("adler_dreams"),
]

# —–––– Prompt integrado sin citar autores –––––—
ENSPROMPT = """
Toma las mejores ideas de psicología profunda para interpretar este sueño de forma unificada,
clara y cercana. No menciones ni cites nombres, apenas ofrece una sola interpretación cálida y directa.

Sueño del usuario:
\"\"\"
{dream}
\"\"\"

Por favor, responde usando un lenguaje humano, accesible, como si un psicólogo amable te lo explicara,
sin tecnicismos ni referencias bibliográficas.
"""

def interpret_ensemble(dream_text: str, language: str = "es") -> Dict:
    # 1) Recuperar fragmentos relevantes de las tres colecciones
    combined_contexts: List[str] = []
    for retriever in retrievers:
        docs: List[Document] = retriever.get_relevant_documents(dream_text)
        combined_contexts.extend([d.page_content for d in docs])

    # 2) Unir el contexto en un solo bloque (no se mostrará al usuario)
    context_for_model = "\n\n".join(combined_contexts)

    # 3) Formatear prompt en que incluimos contexto oculto + la instrucción
    full_prompt = (
        f"{context_for_model}\n\n"  # contexto interno para RAG
        + ENSPROMPT.format(dream=dream_text)
    )

    # 4) Llamar al LLM con más creatividad
    llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.9)
    result = llm.generate([[HumanMessage(content=full_prompt)]])

    # 5) Extraer la respuesta
    interpretation = result.generations[0][0].message.content.strip()

    return {
        "agent": "ensemble",
        "timestamp": None,
        "text": interpretation,
    }
