# agents/ensemble_agent.py

import os
from langchain import PromptTemplate, LLMChain
from langchain_community.llms import OpenAI
from agents.freud_agent import interpret_freud
from agents.jung_agent  import interpret_jung
from agents.adler_agent import interpret_adler

# 1. Cargar prompt maestro de síntesis
prompt_path = os.path.join(os.path.dirname(__file__), "../prompts/ensemble_prompt.txt")
with open(prompt_path, encoding="utf-8") as f:
    ensemble_prompt = f.read()

# 2. Crear plantilla
#    Aquí las variables serán freud, jung y adler
template = ensemble_prompt + "\n\n[Freud] \"{freud}\"\n[Jung] \"{jung}\"\n[Adler] \"{adler}\"\n\n[Ensemble]"
prompt_template = PromptTemplate(
    input_variables=["freud", "jung", "adler"],
    template=template
)

# 3. Configurar LLM
llm = OpenAI(
    temperature=0.7,
    openai_api_key=os.getenv("OPENAI_API_KEY")
)

# 4. Crear cadena
ensemble_chain = LLMChain(llm=llm, prompt=prompt_template)

def interpret_ensemble(dream: str) -> str:
    """
    Llama a los tres agentes, recoge sus salidas y genera la síntesis.
    """
    # Llamadas a cada agente
    out_freud = interpret_freud(dream)
    out_jung  = interpret_jung(dream)
    out_adler = interpret_adler(dream)

    # Llamada al sintetizador
    return ensemble_chain.run(
        freud=out_freud,
        jung =out_jung,
        adler=out_adler
    )
