# agents/orchestrator.py
from agents.freud_agent import freud_interpretation
from agents.jung_agent import jung_interpretation
from agents.adler_agent import adler_interpretation
from agents.ensemble_agent import ensemble_interpretation
from agents.formatter_agent import format_final_response

def interpret_dream(dream_text: str, language: str = "es") -> str:
    """
    Orquesta las interpretaciones de Freud, Jung y Adler,
    luego las combina con el Ensemble Agent y las entrega
    con formato final mediante el Formatter Agent.
    """
    try:
        # Paso 1: Interpretaciones individuales
        freud_result = freud_interpretation(dream_text, language)
        jung_result = jung_interpretation(dream_text, language)
        adler_result = adler_interpretation(dream_text, language)

        # Paso 2: Ensamblar con el agente Ensemble
        ensemble_result = ensemble_interpretation(
            dream_text,
            freud_result,
            jung_result,
            adler_result,
            language
        )

        # Paso 3: Formatear salida con el Formatter
        final_output = format_final_response(ensemble_result, language)
        return final_output

    except Exception as e:
        return f"⚠️ Error en la interpretación: {str(e)}"
