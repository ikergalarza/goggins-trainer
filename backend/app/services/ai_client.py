"""Cliente Claude compartido para todos los servicios IA."""
import logging
from typing import Optional
from anthropic import Anthropic
from app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-4-8"
FAST_MODEL = "claude-haiku-4-5-20251001"

_client: Optional[Anthropic] = None


def get_client() -> Anthropic:
    """Devuelve un cliente Claude singleton. Levanta error si no hay API key."""
    global _client
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY no está configurada. Añádela en las variables de entorno."
        )
    if _client is None:
        _client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


def complete(
    system: str,
    user_message: str,
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 2048,
    temperature: float = 0.7,
) -> str:
    """Helper simple para un prompt user/system de una sola vuelta."""
    client = get_client()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )
    # La respuesta puede contener múltiples bloques; concatenamos texto
    parts = []
    for block in response.content:
        if hasattr(block, "text"):
            parts.append(block.text)
    return "".join(parts)
