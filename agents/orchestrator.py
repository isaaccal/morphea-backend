import os
from typing import Any, Dict, Optional

# === OpenAI opcional (no falla si no hay clave) ===
_USE_OPENAI = bool(os.getenv("OPENAI_API_KEY"))
_OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

if _USE_OPENAI:
    try:
        from openai import OpenAI
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    except Exception:
        _USE_OPENAI = False
        _client = None


# ============================
# Interpretación base (fallback)
# ============================
def _fallback_interpretation(text: str, language: str = "es") -> str:
    """Interpretación determinista simple cuando no hay OpenAI."""
    text = (text or "").strip()
    if not text:
        return "No se proporcionó contenido del sueño."

    if language.startswith("en"):
        return (
            "Freudian lens: The dream may reflect repressed wishes and unresolved tensions.\n"
            "Jungian lens: Notice symbols pointing to individuation and the shadow.\n"
            "Adlerian lens: Consider feelings of inferiority/striving for significance.\n"
            "Actionable note: Write the dream on waking; track recurring symbols and emotions."
        )

    # Español por defecto
    return (
        "Enfoque freudiano: el sueño puede reflejar deseos reprimidos y tensiones no resueltas.\n"
        "Enfoque junguiano: observa símbolos que apunten a individuación y a la sombra.\n"
        "Enfoque adleriano: considera sentimientos de inferioridad y tu afán de logro.\n"
        "Siguiente paso: registra el sueño al despertar y anota símbolos/emociones recurrentes."
    )


def _openai_interpretation(text: str, language: str = "es") -> str:
    """Interpretación con OpenAI si está disponible."""
    if not _USE_OPENAI or not _client:
        return _fallback_interpretation(text, language)

    system = (
        "Eres un analista de sueños profesional. Interpreta de forma breve y útil "
        "usando tres lentes: Freud (deseos/tensiones), Jung (símbolos/arquetipos/individuación) "
        "y Adler (sentido de pertenencia, metas, estilo de vida). Da recomendaciones prácticas. "
        "No inventes datos del soñante."
    )
    user = (
        f"Idioma: {language}\n"
        f"Sueño:\n{text}\n\n"
        "Devuelve en 3–5 párrafos con etiquetas claras: Freud, Jung, Adler, y Recomendaciones."
    )

    resp = _client.chat.completions.create(
        model=_OPENAI_MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.7,
    )
    return resp.choices[0].message.content.strip()


# ==========================================
# Núcleo “ensemble” con firma flexible/robusta
# ==========================================
def ensemble_interpretation(
    dream_text: str,
    language: str = "es",
    *,
    user_context: Optional[Dict[str, Any]] = None,
    max_words: int = 350,
) -> str:
    """
    Genera una interpretación integrando Freud/Jung/Adler.
    Firma estable y con kwargs para evitar romper llamadas futuras.
    """
    # El parámetro max_words está por si lo quieres usar en prompts; de momento no limitamos duro.
    text = (dream_text or "").strip()
    if not text:
        return "No se proporcionó contenido del sueño."

    try:
        return _openai_interpretation(text, language)
    except Exception as e:
        # Último recurso: nunca tirar 500 al caller
        return f"⚠️ Modo seguro (sin IA): { _fallback_interpretation(text, language) }"


# ==========================================
# Adaptador de compatibilidad: interpret_dream
# ==========================================
def interpret_dream(*args, **kwargs) -> str:
    """
    Adaptador que soporta llamadas antiguas y nuevas.

    Usos soportados:
        interpret_dream(text, language='es')
        interpret_dream(text)                          # idioma por defecto
        interpret_dream(text, name, email, language)   # firma antigua con 4-5 posicionales
        interpret_dream(dream_text='...', language='es', user_context={...})

    Así evitamos errores del tipo: “takes from 1 to 2 positional arguments but 5 were given”.
    """
    # Caso nuevo/ideal: dream_text como kw
    dream_text = kwargs.get("dream_text")
    language = kwargs.get("language", "es")

    if dream_text is None:
        # Usos posicionales
        if not args:
            return "No se proporcionó contenido del sueño."
        # args[0] siempre lo tratamos como texto
        dream_text = args[0]
        # Si viene firma antigua: (text, name, email, language, ...)
        if len(args) >= 4 and isinstance(args[3], str):
            language = args[3]

    # Pasar kwargs “extra” de forma segura
    user_context = kwargs.get("user_context")
    max_words = kwargs.get("max_words", 350)

    return ensemble_interpretation(
        dream_text=dream_text,
        language=language,
        user_context=user_context,
        max_words=max_words,
    )
