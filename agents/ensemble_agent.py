# agents/ensemble_agent.py

import os
from dotenv import load_dotenv
load_dotenv()

from typing import Dict, List
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores import PGVector
from langchain_openai.chat_models import ChatOpenAI
from langchain.schema import Document, HumanMessage

# —–––– Configuración de RAG para cada autor –––––—
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

# —–––– Nueva plantilla de prompt más humana y conjunta –––––—
ENSPROMPT = """
Estamos integrando tres perspectivas de psicología profunda (Freud, Jung, Adler) para ofrecerte una sola interpretación clara y cercana.

— Freud aporta ideas sobre deseos internos, simbolismos y defensas.
— Jung aporta nociones de arquetipos, inconsciente colectivo y significado personal.
— Adler aporta énfasis en metas de vida, sentido de pertenencia y superación.

Tu sueño:
\"\"\"
{dream}
\"\"\"

Con base en esas tres corrientes, por favor:
1. Da una **única** interpretación que combine lo mejor de cada enfoque.
2. Usa un **lenguaje cálido y accesible**, como si un psicólogo amable te lo explicara.
3. Evita tecnicismos y no citemos páginas ni textos literales.

Gracias por compartir tu sueño; aquí va la interpretación:
"""

def interpret_ensemble(dream_text: str, language: str = "es") -> Dict:
    # 1) Recuperar contexto de cada escuela
    contexts: Dict[str, str] = {}
    for author, retriever in retrievers.items():
        docs: List[Document] = retriever.get_relevant_documents(dream_text)
        contexts[author] = "\n\n".join(d.page_content for d in docs)

    # 2) Incorporar los contextos en el prompt
    prompt = ENSPROMPT.format(dream=dream_text)

    # 3) Llamar al LLM en modo más creativo
    llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.9)
    result = llm.generate([[HumanMessage(content=prompt)]])

    # 4) Extraer la respuesta
    interpretation = result.generations[0][0].message.content.strip()

    return {
        "agent": "ensemble",
        "timestamp": None,
        "text": interpretation,
    }
