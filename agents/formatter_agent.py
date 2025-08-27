# agents/formatter_agent.py

import os
from dotenv import load_dotenv
load_dotenv()

from typing import Dict, Any
from langchain_openai.chat_models import ChatOpenAI
from langchain.schema import HumanMessage

# —–––– Formatter Agent –––––—
# Recibe un texto (interpretación cruda) y devuelve una versión
# más breve, cálida y fácil de leer, sin tecnicismos ni “voz de robot”.

def format_final_response(text: str, language: str = "es") -> Dict[str, Any]:
    """
    Toma la interpretación completa de un sueño y la convierte en un párrafo
    muy amigable y conciso.

    :param text: Interpretación original (raw) producida por ensemble_agent.
    :param language: Código de idioma ("es" o "en").
    :returns: Un dict con el agente y el texto formateado.
    """
    # 1) Prepara el prompt de formateo
    if language.lower().startswith("en"):
        prompt = (
            "Please rewrite the following dream interpretation in one warm, clear paragraph, "
            "using friendly, everyday English and no technical jargon:\n\n"
            + text
        )
    else:
        prompt = (
            "Por favor, reescribe esta interpretación del sueño en un solo párrafo "
            "cálido y claro, con un lenguaje cercano y sin tecnicismos:\n\n"
            + text
        )

    # 2) Llama al LLM
    llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.8)
    result = llm.generate([[HumanMessage(content=prompt)]])

    # 3) Extrae la respuesta formateada
    friendly = result.generations[0][0].message.content.strip()

    return {
        "agent": "formatter",
        "text": friendly,
    }
