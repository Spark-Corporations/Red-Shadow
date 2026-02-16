"""
BloodHound MCP Server — Active Directory domain analysis.
"""

from __future__ import annotations

import json
from typing import Any

from .base import BaseMCPServer, ToolSchema


class BloodHoundServer(BaseMCPServer):
    def __init__(self, session_manager=None):
        super().__init__(session_manager, name="bloodhound")

    def get_tools(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name="bloodhound_collect",
                description="Collect Active Directory data using SharpHound/BloodHound-python",
                parameters={
                    "type": "object",
                    "properties": {
                        "target": {"type": "string", "description": "Domain controller or domain"},
                        "method": {"type": "string", "enum": ["sharphound", "bloodhound-python"]},
                        "collection": {"type": "string", "description": "Collection methods (All, Default, Session, etc.)"},
                        "username": {"type": "string"},
                        "password": {"type": "string"},
                        "extra_args": {"type": "string"},
                    },
                    "required": ["target"],
                },
            ),
            ToolSchema(
                name="bloodhound_query",
                description="Query BloodHound for attack paths",
                parameters={
                    "type": "object",
                    "properties": {
                        "query_type": {
                            "type": "string",
                            "enum": [
                                "shortest_path_to_da", "kerberoastable",
                                "asreproastable", "domain_admins",
                                "unconstrained_delegation", "custom",
                            ],
                        },
                        "custom_query": {"type": "string", "description": "Custom Cypher query"},
                    },
                },
            ),
        ]

    def build_command(self, tool_name: str = "bloodhound_collect", **params) -> str:
        if tool_name == "bloodhound_collect":
            target = params.get("target", "")
            method = params.get("method", "bloodhound-python")
            collection = params.get("collection", "All")

            if method == "bloodhound-python":
                parts = ["bloodhound-python", "-d", target, "-c", collection]
                if u := params.get("username"):
                    parts.extend(["-u", u])
                if p := params.get("password"):
                    parts.extend(["-p", p])
            else:
                parts = ["SharpHound.exe", f"--CollectionMethods {collection}"]
                parts.append(f"--Domain {target}")

            if extra := params.get("extra_args"):
                parts.append(extra)
            return " ".join(parts)

        elif tool_name == "bloodhound_query":
            qt = params.get("query_type", "shortest_path_to_da")
            cypher_queries = {
                "shortest_path_to_da": "MATCH p=shortestPath((u:User)-[*1..]->(g:Group {name:'DOMAIN ADMINS@DOMAIN.LOCAL'})) RETURN p",
                "kerberoastable": "MATCH (u:User {hasspn:true}) RETURN u.name,u.serviceprincipalnames",
                "asreproastable": "MATCH (u:User {dontreqpreauth:true}) RETURN u.name",
                "domain_admins": "MATCH (u:User)-[:MemberOf*1..]->(g:Group {name:'DOMAIN ADMINS@DOMAIN.LOCAL'}) RETURN u.name",
                "unconstrained_delegation": "MATCH (c:Computer {unconstraineddelegation:true}) RETURN c.name",
            }
            query = params.get("custom_query", cypher_queries.get(qt, ""))
            return f'cypher-shell -u neo4j -p bloodhound "{query}"'

        return ""

    def parse_output(self, tool_name: str, raw_output: str) -> dict[str, Any]:
        if tool_name == "bloodhound_collect":
            files_collected = []
            for line in raw_output.split("\n"):
                if ".json" in line.lower() or "done" in line.lower():
                    files_collected.append(line.strip()[:200])
            return {"status": "collected", "output_files": files_collected}
        return {"raw": raw_output[:4000]}
