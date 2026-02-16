"""
ProxyServer — Reverse proxy that intercepts Anthropic-format API calls and
translates them to OpenAI-compatible /v1/chat/completions for the Kaggle endpoint.

Why:
  Claude Code CLI sends requests in Anthropic format (anthropic.com/v1/messages).
  Our Kaggle Phi-4 server speaks OpenAI format (/v1/chat/completions).
  This proxy transparently:
    1. Listens on localhost:8080 (or ANTHROPIC_BASE_URL)
    2. Receives Anthropic-format requests from Claude Code
    3. Translates to OpenAI format
    4. Forwards to the ngrok Phi-4 endpoint
    5. Translates the response back to Anthropic format
    6. Returns to Claude Code — it never knows the difference

Usage:
    # Terminal 1: Start proxy
    python -m redclaw.proxy.server --backend https://0b2f-34-29-72-116.ngrok-free.app

    # Terminal 2: Set Claude Code to use the proxy
    export ANTHROPIC_BASE_URL=http://localhost:8080
    claude

Architecture:
    Claude Code → Anthropic API format → ProxyServer → OpenAI format → ngrok → Phi-4
                                                     ←  translate  ←
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from typing import Any, Optional

logger = logging.getLogger("redclaw.proxy.server")

try:
    from aiohttp import web
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False


# ── Format Translators ────────────────────────────────────────────────────────

def anthropic_to_openai(body: dict[str, Any]) -> dict[str, Any]:
    """
    Translate an Anthropic /v1/messages request to OpenAI /v1/chat/completions.

    Anthropic format:
      {"model": "claude-...", "max_tokens": 4096, "system": "...",
       "messages": [{"role": "user", "content": "..."}]}

    OpenAI format:
      {"model": "phi-4", "max_tokens": 4096,
       "messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]}
    """
    messages: list[dict[str, Any]] = []

    # System prompt → first message
    if system := body.get("system"):
        if isinstance(system, str):
            messages.append({"role": "system", "content": system})
        elif isinstance(system, list):
            # Anthropic allows system as list of content blocks
            text = " ".join(
                b.get("text", "") for b in system if b.get("type") == "text"
            )
            if text:
                messages.append({"role": "system", "content": text})

    # Convert messages
    for msg in body.get("messages", []):
        role = msg.get("role", "user")
        content = msg.get("content", "")

        # Anthropic uses content blocks: [{"type": "text", "text": "..."}]
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        # Tool call in assistant message
                        pass
                    elif block.get("type") == "tool_result":
                        text_parts.append(
                            f"[Tool Result: {block.get('tool_use_id', '')}]\n"
                            f"{block.get('content', '')}"
                        )
                elif isinstance(block, str):
                    text_parts.append(block)
            content = "\n".join(text_parts) if text_parts else ""

        messages.append({"role": role, "content": content})

    # Build OpenAI payload
    payload: dict[str, Any] = {
        "model": body.get("model", "phi-4"),
        "messages": messages,
        "max_tokens": body.get("max_tokens", 4096),
        "temperature": body.get("temperature", 0.1),
        "stream": body.get("stream", False),
    }

    # Convert tools
    if tools := body.get("tools"):
        openai_tools = []
        for tool in tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {}),
                },
            })
        payload["tools"] = openai_tools
        payload["tool_choice"] = "auto"

    # Top-p, stop sequences
    if top_p := body.get("top_p"):
        payload["top_p"] = top_p
    if stop := body.get("stop_sequences"):
        payload["stop"] = stop

    return payload


def openai_to_anthropic(data: dict[str, Any], model_override: str = "") -> dict[str, Any]:
    """
    Translate OpenAI /v1/chat/completions response to Anthropic /v1/messages format.

    OpenAI → Anthropic response mapping:
      choices[0].message.content → content[{type: "text", text: "..."}]
      choices[0].message.tool_calls → content[{type: "tool_use", ...}]
      choices[0].finish_reason → stop_reason
    """
    choice = data.get("choices", [{}])[0]
    message = choice.get("message", {})
    finish = choice.get("finish_reason", "end_turn")

    # Map finish reasons
    stop_reason_map = {
        "stop": "end_turn",
        "length": "max_tokens",
        "tool_calls": "tool_use",
        "content_filter": "end_turn",
    }
    stop_reason = stop_reason_map.get(finish, "end_turn")

    # Build content blocks
    content_blocks: list[dict[str, Any]] = []

    if text := message.get("content"):
        content_blocks.append({"type": "text", "text": text})

    if tool_calls := message.get("tool_calls"):
        for tc in tool_calls:
            func = tc.get("function", {})
            try:
                args = json.loads(func.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}
            content_blocks.append({
                "type": "tool_use",
                "id": tc.get("id", f"toolu_{uuid.uuid4().hex[:12]}"),
                "name": func.get("name", ""),
                "input": args,
            })

    # Ensure at least one content block
    if not content_blocks:
        content_blocks.append({"type": "text", "text": ""})

    # Usage
    usage_in = data.get("usage", {})

    return {
        "id": f"msg_{uuid.uuid4().hex[:20]}",
        "type": "message",
        "role": "assistant",
        "model": model_override or data.get("model", "phi-4"),
        "content": content_blocks,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage_in.get("prompt_tokens", 0),
            "output_tokens": usage_in.get("completion_tokens", 0),
        },
    }


def openai_chunk_to_anthropic_event(chunk: dict[str, Any], idx: int, msg_id: str) -> list[str]:
    """Convert a single OpenAI streaming chunk to Anthropic SSE events."""
    events = []
    
    if idx == 0:
        # Send message_start
        events.append(json.dumps({
            "type": "message_start",
            "message": {
                "id": msg_id,
                "type": "message",
                "role": "assistant",
                "model": "phi-4",
                "content": [],
                "stop_reason": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
        }))
        # Content block start
        events.append(json.dumps({
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": ""},
        }))

    delta = chunk.get("choices", [{}])[0].get("delta", {})
    finish = chunk.get("choices", [{}])[0].get("finish_reason")

    if text := delta.get("content"):
        events.append(json.dumps({
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": text},
        }))

    if finish:
        events.append(json.dumps({
            "type": "content_block_stop",
            "index": 0,
        }))
        events.append(json.dumps({
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn"},
            "usage": {"output_tokens": 0},
        }))
        events.append(json.dumps({"type": "message_stop"}))

    return events


# ── Proxy Server ──────────────────────────────────────────────────────────────

class ProxyServer:
    """
    Reverse proxy translating Anthropic API → OpenAI API → Kaggle Phi-4.

    Listens on localhost and exposes:
      POST /v1/messages  (Anthropic format → translated → forwarded)
      GET  /health       (proxy health check)
    """

    def __init__(
        self,
        backend_url: str,
        host: str = "127.0.0.1",
        port: int = 8080,
        model_name: str = "phi-4",
    ):
        if not HAS_AIOHTTP:
            raise ImportError("aiohttp required: pip install aiohttp")

        self.backend_url = backend_url.rstrip("/")
        self.host = host
        self.port = port
        self.model_name = model_name
        self._request_count = 0
        self._app: Optional[web.Application] = None
        logger.info(
            f"ProxyServer: {host}:{port} → {self.backend_url}"
        )

    def _create_app(self) -> web.Application:
        app = web.Application()
        app.router.add_post("/v1/messages", self._handle_messages)
        app.router.add_get("/health", self._handle_health)
        app.router.add_get("/v1/models", self._handle_models)
        # Catch-all for other Anthropic endpoints
        app.router.add_route("*", "/{path:.*}", self._handle_passthrough)
        return app

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({
            "status": "ok",
            "proxy": "redclaw-anthropic-to-openai",
            "backend": self.backend_url,
            "requests_served": self._request_count,
        })

    async def _handle_models(self, request: web.Request) -> web.Response:
        """Return model list in Anthropic-ish format."""
        return web.json_response({
            "data": [
                {
                    "id": self.model_name,
                    "object": "model",
                    "created": 1700000000,
                    "owned_by": "redclaw",
                }
            ]
        })

    async def _handle_messages(self, request: web.Request) -> web.Response:
        """
        Main proxy handler: Anthropic /v1/messages → OpenAI /v1/chat/completions.
        """
        self._request_count += 1

        try:
            body = await request.json()
        except Exception as e:
            return web.json_response(
                {"error": {"type": "invalid_request", "message": str(e)}},
                status=400,
            )

        is_stream = body.get("stream", False)

        # Translate Anthropic → OpenAI format
        openai_payload = anthropic_to_openai(body)
        openai_payload["model"] = self.model_name  # Force our model

        logger.info(
            f"[#{self._request_count}] Proxying: "
            f"{len(openai_payload.get('messages', []))} messages, "
            f"stream={is_stream}, "
            f"tools={len(openai_payload.get('tools', []))}"
        )

        backend_url = f"{self.backend_url}/v1/chat/completions"
        headers = {"Content-Type": "application/json"}

        if is_stream:
            return await self._handle_stream(openai_payload, backend_url, headers)
        else:
            return await self._handle_non_stream(openai_payload, backend_url, headers)

    async def _handle_non_stream(
        self, payload: dict, url: str, headers: dict
    ) -> web.Response:
        """Forward non-streaming request and translate response."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.error(f"Backend error: {resp.status} — {text[:300]}")
                        return web.json_response(
                            {"error": {"type": "backend_error", "message": text[:500]}},
                            status=resp.status,
                        )
                    data = await resp.json()

            # Translate OpenAI → Anthropic
            anthropic_resp = openai_to_anthropic(data, self.model_name)
            return web.json_response(anthropic_resp)

        except Exception as e:
            logger.error(f"Proxy error: {e}")
            return web.json_response(
                {"error": {"type": "proxy_error", "message": str(e)}},
                status=502,
            )

    async def _handle_stream(
        self, payload: dict, url: str, headers: dict
    ) -> web.StreamResponse:
        """Forward streaming request with event translation."""
        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
        await response.prepare(request=None)  # Will be set by aiohttp

        msg_id = f"msg_{uuid.uuid4().hex[:20]}"
        chunk_idx = 0

        try:
            async with aiohttp.ClientSession() as session:
                payload["stream"] = True
                async with session.post(
                    url, json=payload, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    async for line in resp.content:
                        line_str = line.decode("utf-8").strip()
                        if not line_str.startswith("data: "):
                            continue
                        data_str = line_str[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            events = openai_chunk_to_anthropic_event(
                                chunk, chunk_idx, msg_id
                            )
                            for event in events:
                                await response.write(
                                    f"event: message\ndata: {event}\n\n".encode()
                                )
                            chunk_idx += 1
                        except json.JSONDecodeError:
                            continue

        except Exception as e:
            logger.error(f"Stream proxy error: {e}")

        return response

    async def _handle_passthrough(self, request: web.Request) -> web.Response:
        """
        Handle any requests not matched by explicit routes.
        Returns success responses for auth/validation endpoints so
        Claude Code's API key check passes through the proxy.
        """
        path = request.path.lower()
        logger.info(f"Passthrough: {request.method} {request.path}")

        # Auth/validation endpoints — return success so Claude Code
        # accepts the dummy API key and skips login
        if "auth" in path or "oauth" in path or "token" in path or "login" in path:
            return web.json_response({
                "status": "ok",
                "authenticated": True,
                "type": "api_key",
            })

        # Account/org info — Claude Code may check this
        if "account" in path or "organization" in path or "org" in path:
            return web.json_response({
                "id": "org_redclaw",
                "name": "RedClaw Proxy",
                "type": "organization",
            })

        # API key validation — some Claude Code versions POST here
        if "api_key" in path or "apikey" in path or "keys" in path:
            return web.json_response({
                "valid": True,
                "type": "api_key",
                "id": "sk-redclaw",
            })

        # Beta/versioned endpoints — return empty success
        if path.startswith("/v1/") or path.startswith("/beta/"):
            return web.json_response({"type": "ok", "data": []})

        return web.json_response(
            {"error": {"type": "not_found", "message": f"Unknown endpoint: {request.path}"}},
            status=404,
        )

    async def start(self) -> None:
        """Start the proxy server."""
        self._app = self._create_app()
        runner = web.AppRunner(self._app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        logger.info(f"Proxy server started: http://{self.host}:{self.port}")
        print(
            f"\n{'='*60}\n"
            f"🔀 RedClaw Reverse Proxy ACTIVE\n"
            f"{'='*60}\n"
            f"  Listen:  http://{self.host}:{self.port}\n"
            f"  Backend: {self.backend_url}\n"
            f"  Model:   {self.model_name}\n\n"
            f"  📡 Set Claude Code to use this proxy:\n"
            f'    export ANTHROPIC_BASE_URL="http://{self.host}:{self.port}"\n'
            f"    claude\n"
            f"{'='*60}\n"
        )

    def run(self) -> None:
        """Run the proxy server (blocking)."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.start())
            loop.run_forever()
        except KeyboardInterrupt:
            logger.info("Proxy server shutting down...")
        finally:
            loop.close()


def start_proxy(
    backend_url: str,
    host: str = "127.0.0.1",
    port: int = 8080,
    model_name: str = "phi-4",
) -> None:
    """Convenience function to start the proxy server."""
    proxy = ProxyServer(
        backend_url=backend_url,
        host=host,
        port=port,
        model_name=model_name,
    )
    proxy.run()


# ── CLI Entry Point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="RedClaw Reverse Proxy — Anthropic API → OpenAI API translator"
    )
    parser.add_argument(
        "--backend", "-b",
        default=os.environ.get(
            "REDCLAW_LLM_URL",
            "https://0b2f-34-29-72-116.ngrok-free.app"
        ),
        help="Backend LLM URL (ngrok endpoint)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Listen host")
    parser.add_argument("--port", "-p", type=int, default=8080, help="Listen port")
    parser.add_argument("--model", "-m", default="phi-4", help="Model name to report")
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    start_proxy(
        backend_url=args.backend,
        host=args.host,
        port=args.port,
        model_name=args.model,
    )


if __name__ == "__main__":
    main()
