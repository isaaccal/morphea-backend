# agents/jung_agent.py

import os
from langchain import PromptTemplate, LLMChain
from langchain_community.llms import OpenAI

# 1. Carga prompt
prompt_path = os.path.join(os.path.dirname(__file__), "../prompts/jung_prompt.txt")
with open(prompt_path, encoding="utf-8") as f:
    jung_prompt = f.read()

# 2. Plantilla
template = jung_prompt + "\n\n[Usuario] \"{dream}\"\n\n[Jung]"
prompt_template = PromptTemplate(input_variables=["dream"], template=template)

# 3. LLM
llm = OpenAI(
    temperature=0.7,
    openai_api_key=os.getenv("OPENAI_API_KEY")
)

# 4. Cadena
jung_chain = LLMChain(llm=llm, prompt=prompt_template)

def interpret_jung(dream: str) -> str:
    """Llama al agente Jung y retorna su interpretación."""
    return jung_chain.run(dream=dream)
