import json
import httpx
from typing import AsyncGenerator, Dict, Any, List
from app.config import settings

async def stream_chat_completion(
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 1024
) -> AsyncGenerator[str, None]:
    url = f"{settings.llm_api_base}/chat/completions"
    payload = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True
    }

    async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
        try:
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code != 200:
                    err_msg = f"LLM server error: HTTP {response.status_code}"
                    yield f"Error de comunicación con el modelo: {err_msg}"
                    return

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
        except httpx.ConnectError:
            yield "No fue posible conectar con el servidor local de IA (llama-server offline)."
        except httpx.TimeoutException:
            yield "Tiempo de espera agotado esperando la respuesta del modelo local."
        except Exception as e:
            yield f"Error inesperado al conectar con el asistente: {str(e)}"
