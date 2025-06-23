# agents/adler_agent.py

import os
from langchain import PromptTemplate, LLMChain
from langchain_community.llms import OpenAI

# 1. Carga el prompt maestro desde prompts/adler_prompt.txt
prompt_path = os.path.join(os.path.dirname(__file__), "../prompts/adler_prompt.txt")
with open(prompt_path, encoding="utf-8") as f:
    adler_prompt = f.read()

# 2. Construye la plantilla de prompt
template = adler_prompt + "\n\n[Usuario] \"{dream}\"\n\n[Adler]"
prompt_template = PromptTemplate(
    input_variables=["dream"],
    template=template
)

# 3. Configura el LLM
llm = OpenAI(
    temperature=0.7,
    openai_api_key=os.getenv("OPENAI_API_KEY")
)

# 4. Crea la cadena
adler_chain = LLMChain(llm=llm, prompt=prompt_template)

def interpret_adler(dream: str) -> str:
    """
    Llama al agente Adler y devuelve la interpretación del sueño.
    """
    return adler_chain.run(dream=dream)
