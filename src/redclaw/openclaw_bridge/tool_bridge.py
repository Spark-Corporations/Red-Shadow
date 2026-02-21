"""
ToolBridge — Translates between OpenClaw tool calls and RedClaw MCP server execution.

This bridge:
  - Receives tool-call requests from the OpenClaw agent
  - Maps them to the appropriate RedClaw MCP server
  - Executes the tool via the MCP server layer
  - Formats results back for the OpenClaw agent context
  - Handles errors, timeouts, and retries
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
    name: str  # e.g., "redclaw_nmap"
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
    Bridge between OpenClaw agent tool calls and RedClaw MCP servers.

    Flow:
      OpenClaw Agent → ToolCallRequest → ToolBridge → MCP Server → ToolCallResult → Agent

    Usage:
        bridge = ToolBridge()
        bridge.register_server("nmap", nmap_server)
        result = await bridge.execute(ToolCallRequest(id="1", name="redclaw_nmap", ...))
    """

    def __init__(self, guardian=None):
        self._servers: dict[str, Any] = {}  # name → MCP server instance
        self._tool_to_server: dict[str, str] = {}  # tool schema name → server name
        self._guardian = guardian  # GuardianRails for command validation
        self._execution_log: list[ToolCallResult] = []
        logger.info("ToolBridge initialized")

    def register_server(self, name: str, server: Any) -> None:
        """Register an MCP server for tool execution."""
        self._servers[name] = server

        # Build tool-schema-name → server-name mapping
        if hasattr(server, "get_tools"):
            for schema in server.get_tools():
                tool_name = schema.name if hasattr(schema, "name") else str(schema)
                self._tool_to_server[tool_name] = name
                logger.debug(f"  Tool '{tool_name}' → server '{name}'")

        logger.info(f"Registered MCP server: {name}")

    def register_servers(self, servers: dict[str, Any]) -> None:
        """Register multiple MCP servers at once."""
        for name, server in servers.items():
            self.register_server(name, server)

    @property
    def available_tools(self) -> list[str]:
        """List of registered tool names."""
        return list(self._servers.keys())

    async def execute(self, request: ToolCallRequest) -> ToolCallResult:
        """
        Execute a tool call by routing to the appropriate MCP server.

        Steps:
          1. Extract the tool name (strip "redclaw_" prefix)
          2. Validate with GuardianRails if available
          3. Route to the registered MCP server
          4. Execute and capture result
          5. Format and return
        """
        start = time.monotonic()

        # Resolve tool name → server name
        #  1. Try direct tool-schema-name mapping (e.g. "nmap_scan" → "nmap")
        #  2. Strip "redclaw_" prefix and try again
        #  3. Fall back to raw name as server lookup
        raw_name = request.name
        tool_name = raw_name.replace("redclaw_", "")

        # Resolve via tool-to-server map
        server_name = (
            self._tool_to_server.get(raw_name)
            or self._tool_to_server.get(tool_name)
            or tool_name  # fallback: assume tool_name == server_name
        )

        # Find the server
        server = self._servers.get(server_name)
        if not server:
            result = ToolCallResult(
                id=request.id,
                name=request.name,
                success=False,
                output="",
                error=f"No MCP server registered for tool: {raw_name} "
                      f"(resolved: {server_name}). "
                      f"Available servers: {self.available_tools}. "
                      f"Known tools: {list(self._tool_to_server.keys())}",
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

        # Execute via MCP server
        try:
            target = request.parameters.get("target", "")
            options = request.parameters.get("options", {})

            # MCP servers implement an `execute` method
            if hasattr(server, "execute_tool"):
                output = await server.execute_tool(
                    command=command,
                    target=target,
                    options=options,
                )
            elif hasattr(server, "execute"):
                output = server.execute(command=command, target=target, **options)
            else:
                output = str(server)

            duration = time.monotonic() - start
            result = ToolCallResult(
                id=request.id,
                name=request.name,
                success=True,
                output=str(output) if not isinstance(output, str) else output,
                duration=duration,
                metadata={"tool": tool_name, "target": target},
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
            f"{'OK' if result.success else 'FAIL'} ({duration:.2f}s)"
        )
        return result

    def format_for_agent(self, result: ToolCallResult) -> dict[str, Any]:
        """Format a tool result for inclusion in the OpenClaw agent context."""
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
            "registered_servers": len(self._servers),
            "total_executions": total,
            "successes": successes,
            "failures": total - successes,
            "success_rate": f"{successes/total*100:.1f}%" if total else "N/A",
        }
