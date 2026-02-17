"""
OpenClaw Runtime — RedClaw's LLM orchestration engine with full ReAct agent loop.

Architecture:
  RedClaw CLI → OpenClawRuntime → Phi4Provider (LLM) → ToolBridge → MCP Servers
                     ↑              ↓                       ↓
                     └── iterate ← tool results ← shell execution

The ReAct Loop:
  1. Send task + context to LLM
  2. LLM responds with text and/or tool_calls
  3. If tool_calls: execute via ToolBridge, feed results back to LLM → goto 2
  4. If no tool_calls (finish): yield final answer, stop
  5. Safety: max_iterations guard prevents infinite loops
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Optional

from .phi4_provider import Phi4Provider, LLMResponse
from .tool_bridge import ToolBridge, ToolCallRequest, ToolCallResult

logger = logging.getLogger("redclaw.openclaw_bridge.runtime")


# ── Data Types ────────────────────────────────────────────────────────────────

@dataclass
class AgentMessage:
    """A message from the RedClaw agent loop."""
    role: str  # "assistant", "tool", "system", "thinking"
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    is_final: bool = False


@dataclass
class RuntimeConfig:
    """Configuration for the OpenClaw runtime."""
    # LLM settings
    llm_endpoint: str = os.environ.get(
        "REDCLAW_LLM_URL",
        "https://0b2f-34-29-72-116.ngrok-free.app"
    )
    llm_model: str = "phi-4"
    llm_api_key: Optional[str] = os.environ.get("REDCLAW_LLM_KEY")
    ollama_endpoint: str = "http://localhost:11434/v1"

    # Agent settings
    max_iterations: int = 30          # Max LLM↔tool cycles per task
    max_tokens: int = 4096            # Max tokens per LLM response
    temperature: float = 0.1          # Low temp for deterministic pentesting
    timeout: int = 600                # Total task timeout (seconds)
    tool_timeout: int = 300           # Per-tool execution timeout

    # Features
    streaming: bool = False           # Stream LLM output token-by-token
    verbose: bool = True              # Yield intermediate steps


# ── Main Runtime ──────────────────────────────────────────────────────────────

class OpenClawRuntime:
    """
    Full ReAct agent loop for autonomous pentesting.

    Usage:
        runtime = OpenClawRuntime()
        await runtime.initialize()
        
        async for msg in runtime.run_task("Scan 10.10.10.5 for open ports"):
            if msg.role == "assistant":
                print(msg.content)
            elif msg.role == "tool":
                print(f"[Tool] {msg.content[:200]}")
    """

    def __init__(self, config: Optional[RuntimeConfig] = None):
        self._config = config or RuntimeConfig()
        self._provider: Optional[Phi4Provider] = None
        self._tool_bridge: Optional[ToolBridge] = None
        self._initialized = False
        self._health_status = "not_initialized"  # REAL: "ready" | "degraded" | "not_initialized"
        self._health_providers: dict[str, Any] = {}  # REAL health check results per provider
        self._iteration_count = 0
        self._total_tasks = 0
        self._conversation: list[dict[str, Any]] = []
        logger.info(
            f"OpenClawRuntime created: endpoint={self._config.llm_endpoint}, "
            f"model={self._config.llm_model}"
        )

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def provider(self) -> Optional[Phi4Provider]:
        return self._provider

    @property
    def tool_bridge(self) -> Optional[ToolBridge]:
        return self._tool_bridge

    # ── Initialization ────────────────────────────────────────────────────

    async def initialize(self) -> dict[str, Any]:
        """
        Initialize runtime: create LLM provider, verify connectivity.
        Returns health status dict.
        """
        # Create provider — normalize URL to avoid double-slash
        endpoint = self._config.llm_endpoint.rstrip("/")
        self._provider = Phi4Provider(
            kaggle_endpoint=endpoint + "/v1"
            if not endpoint.endswith("/v1")
            else endpoint,
            kaggle_api_key=self._config.llm_api_key,
            ollama_endpoint=self._config.ollama_endpoint,
            model=self._config.llm_model,
            max_tokens=self._config.max_tokens,
            temperature=self._config.temperature,
            timeout=self._config.timeout,
        )

        # Health check — this is the REAL connectivity test
        health = self._provider.health_check()
        any_reachable = any(
            v.get("reachable", False) for v in health.values()
        )

        # Store REAL health status — no faking
        self._health_providers = health
        if any_reachable:
            self._health_status = "ready"
            logger.info(f"LLM provider ready: {health}")
        else:
            self._health_status = "degraded"
            logger.warning(
                f"No LLM providers reachable! Health: {health}. "
                "Agent will fail on first task."
            )

        self._initialized = True
        return {
            "status": self._health_status,
            "providers": health,
            "model": self._config.llm_model,
            "max_iterations": self._config.max_iterations,
        }

    def register_tool_bridge(self, tool_bridge: ToolBridge) -> None:
        """Register the ToolBridge for MCP server tool execution."""
        self._tool_bridge = tool_bridge
        logger.info(
            f"ToolBridge registered: {len(tool_bridge.available_tools)} tools available"
        )

    # ── Agent Loop ────────────────────────────────────────────────────────

    async def run_task(
        self,
        task: str,
        context: Optional[dict[str, Any]] = None,
        on_tool_call: Optional[Callable] = None,
    ) -> AsyncIterator[AgentMessage]:
        """
        Execute a pentesting task through the full ReAct agent loop.

        The loop:
          1. Build system prompt + user task
          2. Call LLM with tool definitions
          3. If LLM returns tool_calls → execute each via ToolBridge
          4. Feed tool results back into conversation
          5. Call LLM again → repeat until no more tool_calls or max_iterations
          6. Yield final answer

        Args:
            task: Natural language task (e.g., "Scan 10.10.10.5 for open ports")
            context: Additional context (targets, findings, phase)
            on_tool_call: Optional callback when a tool is called

        Yields:
            AgentMessage for each step (thinking, tool execution, final answer)
        """
        if not self._initialized:
            await self.initialize()

        self._total_tasks += 1
        self._iteration_count = 0
        ctx = context or {}
        task_start = time.monotonic()

        logger.info(f"═══ Task #{self._total_tasks}: {task[:100]}... ═══")

        # ── Step 1: Build conversation history ────────────────────────────
        system_prompt = self._build_system_prompt(ctx)
        self._conversation = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]

        yield AgentMessage(
            role="system",
            content=f"🔴 RedClaw Agent — processing: {task}",
            metadata={"phase": "start", "task_id": self._total_tasks},
        )

        # ── Step 2: Collect tool definitions ──────────────────────────────
        tools = self._get_tool_definitions()

        # ── Step 3: ReAct Loop ────────────────────────────────────────────
        while self._iteration_count < self._config.max_iterations:
            self._iteration_count += 1
            elapsed = time.monotonic() - task_start

            # Timeout check
            if elapsed > self._config.timeout:
                yield AgentMessage(
                    role="system",
                    content=f"⏰ Task timeout after {elapsed:.0f}s",
                    is_final=True,
                    metadata={"reason": "timeout"},
                )
                return

            logger.info(
                f"  Iteration {self._iteration_count}/{self._config.max_iterations} "
                f"({elapsed:.1f}s elapsed)"
            )

            # ── 3a: Call LLM ──────────────────────────────────────────────
            try:
                llm_response: LLMResponse = await self._provider.chat(
                    messages=self._conversation,
                    tools=tools if self._tool_bridge else None,
                )
            except Exception as e:
                logger.error(f"LLM call failed: {e}")
                # Show clean error to user (raw exception may contain HTML pages)
                yield AgentMessage(
                    role="system",
                    content="❌ LLM error: All LLM providers failed — check /link and /agent",
                    is_final=True,
                    metadata={"error": str(e)[:200]},
                )
                return

            # ── 3b: Process LLM text response ─────────────────────────────
            if llm_response.content:
                if self._config.verbose:
                    yield AgentMessage(
                        role="assistant",
                        content=llm_response.content,
                        metadata={
                            "iteration": self._iteration_count,
                            "model": llm_response.model,
                            "latency": f"{llm_response.latency:.2f}s",
                        },
                    )

            # ── 3c: Check for tool calls ──────────────────────────────────
            if not llm_response.tool_calls:
                # No tool calls → LLM is done with the task
                yield AgentMessage(
                    role="assistant",
                    content=llm_response.content or "(no response)",
                    is_final=True,
                    metadata={
                        "iteration": self._iteration_count,
                        "total_time": f"{time.monotonic() - task_start:.2f}s",
                        "finish_reason": llm_response.finish_reason,
                    },
                )
                logger.info(
                    f"  Task complete: {self._iteration_count} iterations, "
                    f"{time.monotonic() - task_start:.1f}s"
                )
                return

            # ── 3d: Execute tool calls ────────────────────────────────────
            # Append assistant message with tool calls to conversation
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": llm_response.content or ""}
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc.get("arguments", {})),
                    },
                }
                for tc in llm_response.tool_calls
            ]
            self._conversation.append(assistant_msg)

            for tc in llm_response.tool_calls:
                tool_name = tc.get("name", "unknown")
                tool_args = tc.get("arguments", {})
                tool_id = tc.get("id", f"call_{uuid.uuid4().hex[:8]}")

                logger.info(f"  🔧 Tool call: {tool_name}({json.dumps(tool_args)[:100]})")

                # Notify callback
                if on_tool_call:
                    on_tool_call(tool_name, tool_args)

                # Yield tool call notification
                yield AgentMessage(
                    role="thinking",
                    content=f"🔧 Calling tool: {tool_name}",
                    tool_calls=[tc],
                    metadata={"iteration": self._iteration_count},
                )

                # Execute via ToolBridge
                if self._tool_bridge:
                    request = ToolCallRequest(
                        id=tool_id,
                        name=tool_name,
                        parameters=tool_args,
                    )
                    result: ToolCallResult = await self._tool_bridge.execute(request)

                    tool_output = result.output if result.success else f"ERROR: {result.error}"
                    tool_success = result.success
                else:
                    # No tool bridge — simulate
                    tool_output = (
                        f"[No ToolBridge registered] Would execute: {tool_name} "
                        f"with args: {json.dumps(tool_args)}"
                    )
                    tool_success = False

                # Yield tool result
                yield AgentMessage(
                    role="tool",
                    content=tool_output[:2000],  # Truncate for display
                    tool_results=[{
                        "tool": tool_name,
                        "success": tool_success,
                        "output_length": len(tool_output),
                    }],
                    metadata={
                        "iteration": self._iteration_count,
                        "tool": tool_name,
                        "success": tool_success,
                    },
                )

                # Feed tool result back into conversation for the LLM
                self._conversation.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": tool_output[:8000],  # Keep context manageable
                })

                logger.info(
                    f"  Tool result: {tool_name} → "
                    f"{'OK' if tool_success else 'FAIL'} "
                    f"({len(tool_output)} chars)"
                )

            # Loop continues → next iteration will send tool results to LLM

        # ── Max iterations reached ────────────────────────────────────────
        yield AgentMessage(
            role="system",
            content=(
                f"⚠️ Max iterations ({self._config.max_iterations}) reached. "
                f"Task may be incomplete."
            ),
            is_final=True,
            metadata={
                "reason": "max_iterations",
                "total_time": f"{time.monotonic() - task_start:.2f}s",
            },
        )

    # ── Internal Helpers ──────────────────────────────────────────────────

    def _build_system_prompt(self, context: dict[str, Any]) -> str:
        """Build the system prompt with RedClaw identity and context."""
        phase = context.get("phase", "autonomous")
        targets = context.get("targets", [])
        findings = context.get("findings", [])
        scope = context.get("scope", [])

        prompt = (
            "You are RedClaw v2.0, an enterprise autonomous penetration testing agent.\n\n"
            "## Your Identity\n"
            "- Built on OpenClaw runtime with Kaggle Phi-4\n"
            "- You execute pentesting tasks by calling tools and analyzing results\n"
            "- You are methodical, thorough, and safety-conscious\n\n"
            "## Current Context\n"
            f"- Phase: {phase}\n"
            f"- Targets: {', '.join(targets) if targets else 'As specified in task'}\n"
            f"- Scope: {', '.join(scope) if scope else 'As specified in task'}\n"
            f"- Findings so far: {len(findings)}\n\n"
            "## Available Tools\n"
            "Call these tools to execute pentesting operations:\n"
        )

        # Add tool descriptions from bridge
        if self._tool_bridge:
            for tool_name in self._tool_bridge.available_tools:
                prompt += f"- `{tool_name}`: Available for use\n"
        else:
            prompt += (
                "- nmap: Port scanning and service detection\n"
                "- masscan: Ultra-fast port discovery\n"
                "- nuclei: Template-based vulnerability scanning\n"
                "- metasploit: Exploitation framework\n"
                "- sqlmap: SQL injection testing\n"
                "- hydra: Brute-force password attacks\n"
                "- linpeas/winpeas: Privilege escalation enumeration\n"
                "- bloodhound: Active Directory analysis\n"
            )

        prompt += (
            "\n## Rules\n"
            "1. ALWAYS stay within the defined target scope\n"
            "2. NEVER execute destructive commands (rm -rf, mkfs, dd, etc.)\n"
            "3. Log all actions with evidence\n"
            "4. Report findings with CVSS severity (critical/high/medium/low/info)\n"
            "5. Ask for human approval before high-risk operations\n"
            "6. When done, summarize all findings clearly\n"
        )

        if findings:
            prompt += "\n## Previous Findings\n"
            for f in findings[-10:]:
                prompt += f"- [{f.get('severity', 'info')}] {f.get('title', '')}\n"

        return prompt

    def _get_tool_definitions(self) -> list[dict[str, Any]]:
        """Collect tool schemas from all registered MCP servers."""
        if not self._tool_bridge:
            return []

        tools = []
        for server_name, server in self._tool_bridge._servers.items():
            if hasattr(server, "get_tools"):
                for schema in server.get_tools():
                    tools.append(schema.to_dict())
        return tools

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def shutdown(self) -> None:
        """Shutdown the runtime — resets all state including health."""
        self._initialized = False
        self._health_status = "not_initialized"
        self._health_providers = {}
        self._conversation = []
        logger.info("OpenClaw runtime shutdown")

    def get_status(self) -> dict[str, Any]:
        """Get runtime status — returns REAL health, not fake."""
        return {
            "initialized": self._initialized,
            "health": self._health_status,  # REAL: "ready" | "degraded" | "not_initialized"
            "health_providers": self._health_providers,  # Per-provider reachability
            "llm_endpoint": self._config.llm_endpoint,
            "llm_model": self._config.llm_model,
            "total_tasks": self._total_tasks,
            "last_iterations": self._iteration_count,
            "tool_bridge": (
                f"{len(self._tool_bridge.available_tools)} tools"
                if self._tool_bridge else "not registered"
            ),
            "provider_stats": (
                self._provider.get_stats() if self._provider else None
            ),
        }

    def reset_conversation(self) -> None:
        """Clear conversation history for a fresh task."""
        self._conversation = []
        self._iteration_count = 0
