"""
ToolBridge — Translates between OpenClaw tool calls and RedClaw tool wrappers.

This bridge:
  - Receives tool-call requests from the OpenClaw agent
  - Maps them to the appropriate tool wrapper (nmap, nuclei, sqlmap, gobuster, ffuf, bash)
  - Executes the tool via the wrapper (subprocess + OutputCleaner)
  - Formats results back for the OpenClaw agent context
  - Validates commands via GuardianRails
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("redclaw.openclaw_bridge.tool_bridge")


@dataclass
class ToolCallRequest:
    """Incoming tool call from the OpenClaw agent."""
    id: str
    name: str  # e.g., "nmap_scan", "exec_command"
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCallResult:
    """Result of a tool call execution."""
    id: str
    name: str
    success: bool
    output: str
    error: Optional[str] = None
    duration: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class ToolBridge:
    """
    Bridge between OpenClaw agent tool calls and RedClaw tool wrappers.

    Flow:
      OpenClaw Agent → ToolCallRequest → ToolBridge → Wrapper → subprocess → OutputCleaner → ToolCallResult → Agent

    Usage:
        bridge = ToolBridge(guardian=guardian)
        bridge.register_server("nmap", nmap_wrapper)
        bridge.register_server("bash", bash_wrapper)
        result = await bridge.execute(ToolCallRequest(id="1", name="nmap_scan", ...))
    """

    def __init__(self, guardian=None):
        self._servers: dict[str, Any] = {}       # name → tool wrapper instance
        self._tool_to_server: dict[str, str] = {}  # tool schema name → server name
        self._guardian = guardian                    # GuardianRails for command validation
        self._execution_log: list[ToolCallResult] = []
        logger.info("ToolBridge initialized")

    def register_server(self, name: str, server: Any) -> None:
        """Register a tool wrapper for execution."""
        self._servers[name] = server

        # Build tool-schema-name → server-name mapping
        if hasattr(server, "get_tools"):
            for schema in server.get_tools():
                tool_name = schema.name if hasattr(schema, "name") else str(schema)
                self._tool_to_server[tool_name] = name
                logger.debug(f"  Tool '{tool_name}' → wrapper '{name}'")

        logger.info(f"Registered tool wrapper: {name}")

    def register_servers(self, servers: dict[str, Any]) -> None:
        """Register multiple tool wrappers at once."""
        for name, server in servers.items():
            self.register_server(name, server)

    @property
    def available_tools(self) -> list[str]:
        """List of registered tool names."""
        return list(self._tool_to_server.keys())

    async def execute(self, request: ToolCallRequest) -> ToolCallResult:
        """
        Execute a tool call by routing to the appropriate wrapper.

        Steps:
          1. Resolve tool name → wrapper
          2. Validate with GuardianRails if command present
          3. Execute via wrapper.execute(name, params)
          4. Convert CleanedOutput → ToolCallResult
          5. Log and return
        """
        start = time.monotonic()

        # Resolve tool name → wrapper name
        raw_name = request.name
        tool_name = raw_name.replace("redclaw_", "")

        server_name = (
            self._tool_to_server.get(raw_name)
            or self._tool_to_server.get(tool_name)
            or tool_name
        )

        server = self._servers.get(server_name)
        if not server:
            result = ToolCallResult(
                id=request.id,
                name=request.name,
                success=False,
                output="",
                error=f"No wrapper registered for tool: {raw_name}. "
                      f"Available: {list(self._tool_to_server.keys())}",
            )
            self._execution_log.append(result)
            return result

        # Validate with GuardianRails
        command = request.parameters.get("command", "")
        if self._guardian and command:
            validation = self._guardian.validate(command)
            if not validation.allowed:
                result = ToolCallResult(
                    id=request.id,
                    name=request.name,
                    success=False,
                    output="",
                    error=f"Command blocked by GuardianRails: {validation.reasons}",
                    metadata={"risk_level": validation.risk_level.value},
                )
                self._execution_log.append(result)
                logger.warning(f"Tool call blocked: {request.name} — {validation.reasons}")
                return result

        # Execute via wrapper
        try:
            # All wrappers implement: execute(name, params) -> CleanedOutput
            if hasattr(server, "execute"):
                import asyncio
                cleaned = server.execute(raw_name, request.parameters)
                # If the wrapper returns a coroutine, await it
                if asyncio.iscoroutine(cleaned):
                    cleaned = await cleaned

                # Convert CleanedOutput → ToolCallResult
                duration = time.monotonic() - start
                result = ToolCallResult(
                    id=request.id,
                    name=request.name,
                    success=cleaned.success,
                    output=cleaned.to_llm_context(),
                    error="; ".join(cleaned.warnings) if not cleaned.success else None,
                    duration=duration,
                    metadata={
                        "tool": tool_name,
                        "raw_length": cleaned.raw_length,
                        "cleaned_length": cleaned.cleaned_length,
                    },
                )
            else:
                result = ToolCallResult(
                    id=request.id,
                    name=request.name,
                    success=False,
                    output="",
                    error=f"Wrapper {server_name} has no execute method",
                )

        except Exception as e:
            duration = time.monotonic() - start
            result = ToolCallResult(
                id=request.id,
                name=request.name,
                success=False,
                output="",
                error=f"Tool execution error: {type(e).__name__}: {e}",
                duration=duration,
            )
            logger.error(f"Tool execution failed: {request.name} — {e}")

        self._execution_log.append(result)
        logger.info(
            f"Tool executed: {request.name} → "
            f"{'OK' if result.success else 'FAIL'} ({result.duration:.2f}s)"
        )
        return result

    def format_for_agent(self, result: ToolCallResult) -> dict[str, Any]:
        """Format a tool result for inclusion in agent context."""
        return {
            "tool_call_id": result.id,
            "name": result.name,
            "content": result.output if result.success else f"ERROR: {result.error}",
            "success": result.success,
            "duration": f"{result.duration:.2f}s",
        }

    @property
    def execution_log(self) -> list[ToolCallResult]:
        return self._execution_log

    def get_stats(self) -> dict[str, Any]:
        total = len(self._execution_log)
        successes = sum(1 for r in self._execution_log if r.success)
        return {
            "registered_wrappers": len(self._servers),
            "registered_tools": len(self._tool_to_server),
            "total_executions": total,
            "successes": successes,
            "failures": total - successes,
            "success_rate": f"{successes/total*100:.1f}%" if total else "N/A",
        }
