# agents/adler_agent.py
from openai import OpenAI

client = OpenAI()

def adler_interpretation(dream_text: str, language: str = "es") -> str:
    """
    Interpreta un sueño con perspectiva Adleriana.
    Se enfoca en metas, estilo de vida y compensación personal.
    """
    prompt = f"""
    Eres un psicólogo inspirado en Alfred Adler.
    Interpreta el siguiente sueño considerando:
    - Las metas vitales y el sentido de pertenencia del soñante
    - Cómo refleja el sueño sentimientos de inferioridad o compensación
    - Ofrece 2-3 hipótesis interpretativas
    - Da recomendaciones prácticas para la vida cotidiana
    Responde en {language}.

    Sueño:
    {dream_text}
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": "Eres Alfred Adler en un ejercicio de interpretación de sueños."},
                  {"role": "user", "content": prompt}],
        max_tokens=350,
        temperature=0.7,
    )

    return response.choices[0].message.content.strip()
