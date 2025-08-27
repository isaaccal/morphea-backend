# agents/jung_agent.py
from openai import OpenAI

client = OpenAI()

def jung_interpretation(dream_text: str, language: str = "es") -> str:
    """
    Interpreta un sueño con perspectiva Jungiana.
    Se enfoca en arquetipos, símbolos culturales y el inconsciente colectivo.
    """
    prompt = f"""
    Eres un psicólogo inspirado en Carl Jung. 
    Interpreta el siguiente sueño considerando arquetipos y símbolos del inconsciente colectivo.
    - Resume el sueño brevemente
    - Propón 2-3 hipótesis interpretativas
    - Relaciona con símbolos culturales universales
    - Da sugerencias prácticas para la vida del soñante
    Responde en {language}.

    Sueño:
    {dream_text}
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": "Eres Carl Jung en un ejercicio de interpretación de sueños."},
                  {"role": "user", "content": prompt}],
        max_tokens=350,
        temperature=0.7,
    )

    return response.choices[0].message.content.strip()
