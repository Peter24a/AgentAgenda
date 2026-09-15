"""Owner-only read-only MCP transport, launched through authenticated SSH.

Do not expose this process as an anonymous network listener. Its authority comes
from the OS/SSH account permitted to execute it, not from JSON-RPC input.
"""
import asyncio
import json
import logging
import sys

from app.db.session import get_db_context
from app.mcp.server import mcp_server, rpc_error
from app.models.auth import AuthContext

MAX_MESSAGE_BYTES = 1024 * 1024
OWNER = AuthContext(
    user_id="default_user", device_id=None, token_id="stdio-owner-readonly",
    scopes=["mcp:read", "agenda:read", "tasks:read", "memory:read", "documents:read"],
    device_name="Authenticated SSH MCP", platform="stdio",
)
logger = logging.getLogger(__name__)


async def serve(input_stream=None, output_stream=None):
    incoming = input_stream if input_stream is not None else sys.stdin.buffer
    outgoing = output_stream if output_stream is not None else sys.stdout.buffer
    while True:
        raw = await asyncio.to_thread(incoming.readline, MAX_MESSAGE_BYTES + 1)
        if not raw:
            return
        if len(raw) > MAX_MESSAGE_BYTES:
            # Drain only this rejected line using bounded reads before continuing.
            while raw and not raw.endswith(b"\n"):
                raw = await asyncio.to_thread(incoming.readline, MAX_MESSAGE_BYTES + 1)
            response = rpc_error(None, -32600, "Mensaje demasiado grande")
        else:
            try:
                request = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                response = rpc_error(None, -32700, "JSON inválido")
            else:
                try:
                    async with get_db_context() as session:
                        response = await mcp_server.handle_jsonrpc(session, OWNER, request)
                except Exception:
                    # No request payloads, SQL details or credentials on stdout.
                    logger.error("MCP request failed")
                    request_id = request.get("id") if isinstance(request, dict) else None
                    response = rpc_error(request_id, -32603, "Error interno del servidor")
        if response is None:
            continue
        encoded = json.dumps(response, ensure_ascii=False).encode("utf-8")
        if len(encoded) > MAX_MESSAGE_BYTES:
            encoded = json.dumps(rpc_error(response.get("id"), -32603,
                                           "Respuesta demasiado grande; reduzca el alcance")).encode("utf-8")
        outgoing.write(encoded + b"\n")
        outgoing.flush()


def main():
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    asyncio.run(serve())


if __name__ == "__main__":
    main()
