"""Streaming adapter for the authenticated AIlauncher OpenAI gateway."""
import json
from typing import AsyncGenerator, Dict, List

import httpx
from app.config import settings


class LLMError(RuntimeError):
    """A generation failed; never persist this as assistant content."""


def llm_headers() -> dict[str, str]:
    key = settings.llm_api_key.get_secret_value()
    return {"Authorization": f"Bearer {key}"} if key else {}


async def stream_chat_completion(
    messages: List[Dict[str, str]],
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> AsyncGenerator[str, None]:
    payload = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    # Allow the gateway's 60-second admission queue while failing connections fast.
    timeout = httpx.Timeout(settings.llm_timeout_seconds, connect=5.0)
    completed = False
    has_content = False
    try:
        async with httpx.AsyncClient(timeout=timeout, headers=llm_headers()) as client:
            async with client.stream(
                "POST", f"{settings.llm_api_base.rstrip('/')}/chat/completions", json=payload
            ) as response:
                if response.status_code != 200:
                    if response.status_code in (429, 503):
                        raise LLMError("El servicio de IA está ocupado o no disponible. Intenta de nuevo.")
                    raise LLMError(f"Error de comunicación con IA: HTTP {response.status_code}.")
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        completed = True
                        break
                    try:
                        event = json.loads(data)
                        if not isinstance(event, dict) or "error" in event:
                            raise LLMError("El servicio de IA devolvió un error durante la generación.")
                        for choice in event.get("choices", []):
                            if choice.get("finish_reason") == "length":
                                raise LLMError("La respuesta excedió el límite; pide un cambio más breve antes de aprobarlo.")
                            content = choice.get("delta", {}).get("content")
                            if content:
                                if not isinstance(content, str):
                                    raise ValueError("Invalid content")
                                has_content = True
                                yield content
                    except (ValueError, TypeError, AttributeError) as exc:
                        raise LLMError("El servicio de IA devolvió una respuesta inválida.") from exc
        if not completed or not has_content:
            raise LLMError("La respuesta de IA quedó incompleta. Intenta de nuevo.")
    except httpx.TimeoutException as exc:
        raise LLMError("Tiempo de espera agotado esperando la respuesta del modelo local.") from exc
    except httpx.HTTPError as exc:
        raise LLMError("No fue posible completar la conexión con el servicio local de IA.") from exc
