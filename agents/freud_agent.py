# agents/freud_agent.py

import os
from langchain import PromptTemplate, LLMChain
from langchain.llms import OpenAI

# 1. Carga el prompt maestro desde prompts/freud_prompt.txt
prompt_path = os.path.join(os.path.dirname(__file__), "../prompts/freud_prompt.txt")
with open(prompt_path, encoding="utf-8") as f:
    freud_prompt = f.read()

# 2. Construye la plantilla de prompt
#    Asumimos que el LLM recibirá la variable "dream"
template = freud_prompt + "\n\n[Usuario] \"{dream}\"\n\n[Freud]"
prompt_template = PromptTemplate(
    input_variables=["dream"],
    template=template
)

# 3. Configura el LLM con tu clave de OpenAI
#    Puedes ajustar temperature según necesites más o menos creatividad
llm = OpenAI(
    temperature=0.7,
    openai_api_key=os.getenv("OPENAI_API_KEY")
)

# 4. Crea la cadena que une prompt y modelo
freud_chain = LLMChain(
    llm=llm,
    prompt=prompt_template
)

def interpret_freud(dream: str) -> str:
    """
    Llama al agente Freud y devuelve la interpretación del sueño.
    """
    # Ejecuta la cadena con el texto del sueño
    return freud_chain.run(dream=dream)
