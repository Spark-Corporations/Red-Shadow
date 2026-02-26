"""
TeamLead — Master orchestrator for RedClaw V3.1 Agent Teams.

Responsibilities:
  1. Task decomposition (LLM-based)
  2. Teammate spawning with Model Alloy routing
  3. Progress monitoring via Mailbox
  4. Stuck teammate detection and intervention
  5. Result synthesis and report generation
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Optional

from ..memory.knowledge_graph import get_knowledge_graph
from ..memory.memagent import MemAgent
from .mailbox import Mailbox
from .shared_task_list import SharedTaskList
from .lock_manager import LockManager

logger = logging.getLogger("redclaw.agents.team_lead")


class TeamLead:
    """
    Master orchestrator that coordinates all teammates.

    Usage:
        from redclaw.router import OpenRouterClient, ModelAlloyRouter

        client = OpenRouterClient()
        router = ModelAlloyRouter(client)

        team_lead = TeamLead(client, router)
        report = await team_lead.orchestrate("Pentest 10.10.10.5 --parallel")
    """

    # Tool assignments per teammate type
    TOOL_ASSIGNMENTS = {
        "recon": ["nmap", "nuclei", "dirb", "subdomain_enum", "whois"],
        "exploit": ["metasploit", "search_web", "download_poc", "compile_exploit"],
        "validator": ["playwright", "screenshot", "http_client"],
        "binary_analyst": ["ghidra", "radare2", "pattern_matcher"],
        "general": [],
    }

    def __init__(
        self,
        client,
        model_alloy_router,
        working_dir: Optional[str] = None,
    ):
        self.client = client
        self.model_alloy_router = model_alloy_router

        # Core components
        self.shared_task_list = SharedTaskList()
        self.mailbox = Mailbox()
        self.lock_manager = LockManager()
        self.progress_file = MemAgent(working_dir)
        self.knowledge_graph = get_knowledge_graph()

        # State
        self.teammates: list = []
        self.running = False
        self._start_time = 0.0

        # Register team_lead in mailbox
        self.mailbox.register_agent("team_lead")

        logger.info("TeamLead initialized")

    # ═══════════════════════════════════════════════════════════════════════
    # MAIN ORCHESTRATION
    # ═══════════════════════════════════════════════════════════════════════

    async def orchestrate(self, user_request: str) -> dict[str, Any]:
        """
        Main orchestration loop.

        1. Initialize progress
        2. Decompose task into subtasks
        3. Spawn teammates
        4. Monitor progress
        5. Synthesize results
        6. Generate report
        7. Cleanup
        """
        try:
            self.running = True
            self._start_time = time.monotonic()

            # 1. Initialize
            self.progress_file.initialize(user_request)
            logger.info(f"Starting orchestration: {user_request}")

            # 2. Decompose into parallel subtasks
            logger.info("Decomposing task...")
            tasks = await self.decompose_task(user_request)
            logger.info(f"Created {len(tasks)} subtasks")

            # Add to progress file
            self.progress_file.add_pending_tasks(tasks)

            # 3. Add tasks to shared list and spawn teammates
            logger.info(f"Spawning teammates...")
            for task in tasks:
                self.shared_task_list.add_task(
                    task_id=task["id"],
                    description=task["desc"],
                    dependencies=task.get("deps", []),
                    priority=task.get("priority", 0),
                )

            # Create teammate workers
            teammate_tasks = []
            for task in tasks:
                teammate = await self.spawn_teammate(task)
                if teammate:
                    teammate_tasks.append(teammate)

            # 4. Monitor progress
            logger.info("Monitoring progress...")
            await self.monitor_progress()

            # 5. Synthesize
            logger.info("Synthesizing results...")
            results = await self.synthesize_results()

            # 6. Update final status
            self.progress_file.set_status("COMPLETE")

            elapsed = time.monotonic() - self._start_time
            logger.info(f"Orchestration complete: {elapsed:.2f}s")

            return results

        except Exception as e:
            logger.error(f"Orchestration failed: {e}")
            self.progress_file.set_status(f"FAILED: {e}")
            raise

        finally:
            await self.cleanup()
            self.running = False

    # ═══════════════════════════════════════════════════════════════════════
    # TASK DECOMPOSITION
    # ═══════════════════════════════════════════════════════════════════════

    async def decompose_task(self, user_request: str) -> list[dict[str, Any]]:
        """
        Break pentest request into parallel subtasks using Brain model.
        """
        system_prompt = """You are RedClaw Team Lead. Break pentest requests into subtasks.

Rules:
1. Identify INDEPENDENT tasks (can run in parallel)
2. Identify DEPENDENT tasks (must wait for others)
3. Each task needs: id, desc, deps (list of dependency IDs), type (recon/exploit/validator/binary_analyst/general)

Output JSON array ONLY. No explanation."""

        prompt = f"""User Request: {user_request}

Break into subtasks with dependencies.
Output format: [{{"id": "task_1", "desc": "...", "deps": [], "type": "recon"}}, ...]"""

        response = await self.client.call_brain(
            prompt, system_prompt=system_prompt, temperature=0.6
        )

        # Parse JSON from response
        try:
            # Extract JSON array from response
            json_match = response[response.find("["):response.rfind("]") + 1]
            tasks = json.loads(json_match)
        except (json.JSONDecodeError, ValueError):
            # Fallback: create default task list
            logger.warning("Could not parse task decomposition, using defaults")
            tasks = self._default_tasks(user_request)

        return tasks

    @staticmethod
    def _default_tasks(user_request: str) -> list[dict[str, Any]]:
        """Create default task list if LLM decomposition fails."""
        return [
            {"id": "recon_nmap", "desc": f"Nmap scan: {user_request}", "deps": [], "type": "recon"},
            {"id": "recon_nuclei", "desc": f"Nuclei scan: {user_request}", "deps": [], "type": "recon"},
            {"id": "recon_dirb", "desc": f"Directory enumeration: {user_request}", "deps": [], "type": "recon"},
            {"id": "vuln_assess", "desc": "Analyze scan results for vulnerabilities", "deps": ["recon_nmap", "recon_nuclei"], "type": "general"},
            {"id": "exploit_vulns", "desc": "Exploit identified vulnerabilities", "deps": ["vuln_assess"], "type": "exploit"},
            {"id": "validate", "desc": "Validate exploitation results", "deps": ["exploit_vulns"], "type": "validator"},
        ]

    # ═══════════════════════════════════════════════════════════════════════
    # TEAMMATE SPAWNING
    # ═══════════════════════════════════════════════════════════════════════

    async def spawn_teammate(self, task: dict[str, Any]):
        """Create specialized teammate for a task."""
        task_type = task.get("type", "general")
        tools = self.TOOL_ASSIGNMENTS.get(task_type, [])

        # Create lightweight teammate coroutine
        teammate_id = f"teammate_{task['id']}"
        self.mailbox.register_agent(teammate_id)

        async def teammate_worker():
            """Worker coroutine for a single teammate."""
            try:
                # Claim the task
                claimed = self.shared_task_list.claim_task(teammate_id)
                if not claimed:
                    return

                self.progress_file.update_task_status(
                    task["id"], "RUNNING", f"Started by {teammate_id}"
                )

                # Build context
                context = self._build_teammate_context(task, tools)

                # Execute using Model Alloy
                result = await self.model_alloy_router.execute_task(
                    {"id": task["id"], "description": task["desc"]},
                    context=context,
                )

                if result.get("success"):
                    # Mark complete
                    self.shared_task_list.complete_task(
                        task["id"], json.dumps(result)
                    )
                    self.progress_file.update_task_status(
                        task["id"], "COMPLETE", result.get("result", "")[:200]
                    )
                    # Notify team lead
                    self.mailbox.send(teammate_id, "team_lead", {
                        "type": "task_complete",
                        "task_id": task["id"],
                        "summary": result.get("result", "")[:200],
                    })
                else:
                    # Mark failed
                    error = result.get("error", "Unknown error")
                    self.shared_task_list.fail_task(task["id"], error)
                    self.progress_file.update_task_status(
                        task["id"], "FAILED", error
                    )
                    self.mailbox.send(teammate_id, "team_lead", {
                        "type": "error",
                        "task_id": task["id"],
                        "error": error,
                    })

            except Exception as e:
                logger.error(f"Teammate {teammate_id} error: {e}")
                self.shared_task_list.fail_task(task["id"], str(e))
                self.mailbox.send(teammate_id, "team_lead", {
                    "type": "error", "task_id": task["id"], "error": str(e)
                })

        # Launch async
        worker = asyncio.create_task(teammate_worker())
        self.teammates.append({"id": teammate_id, "task": worker, "type": task_type})
        return worker

    def _build_teammate_context(self, task: dict, tools: list[str]) -> str:
        """Build context string for a teammate."""
        progress = self.progress_file.get_context_summary()
        graph_data = self.knowledge_graph.query_natural_language(
            f"Summary of target for task {task['id']}"
        )

        return f"""Previous work: {json.dumps(progress.get('completed_tasks', []), indent=2)}
Key findings: {json.dumps(progress.get('key_findings', []), indent=2)}
Knowledge Graph: {json.dumps(graph_data, indent=2)}
Available tools: {', '.join(tools)}
Your task: {task['desc']}"""

    # ═══════════════════════════════════════════════════════════════════════
    # PROGRESS MONITORING
    # ═══════════════════════════════════════════════════════════════════════

    async def monitor_progress(self):
        """Monitor all teammates and handle messages."""
        while not self.shared_task_list.all_tasks_complete():
            # Check for messages
            messages = self.mailbox.get_messages("team_lead")
            for msg in messages:
                await self._process_message(msg)

            # Check for stuck teammates (no progress in 5 min)
            await self._check_stuck_teammates()

            await asyncio.sleep(2)

        # Wait for all teammate coroutines to finish
        tasks_to_wait = [t["task"] for t in self.teammates if not t["task"].done()]
        if tasks_to_wait:
            await asyncio.gather(*tasks_to_wait, return_exceptions=True)

    async def _process_message(self, msg: dict):
        """Handle incoming teammate messages."""
        msg_type = msg.get("type", "")

        if msg_type == "task_complete":
            logger.info(f"Task {msg.get('task_id')} complete: {msg.get('summary', '')[:80]}")

        elif msg_type == "validation_request":
            logger.info(f"Validation requested for exploit from {msg.get('from')}")

        elif msg_type == "error":
            logger.error(f"Agent {msg.get('from')} error: {msg.get('error')}")

        elif msg_type == "critical_finding":
            logger.critical(f"Critical finding from {msg.get('from')}: {msg.get('finding')}")
            self.progress_file.add_finding(msg.get("finding", ""), "critical")

    async def _check_stuck_teammates(self):
        """Detect teammates that appear stuck."""
        for teammate in self.teammates:
            task = teammate["task"]
            if not task.done():
                # Could add timeout-based detection here
                pass

    # ═══════════════════════════════════════════════════════════════════════
    # RESULT SYNTHESIS
    # ═══════════════════════════════════════════════════════════════════════

    async def synthesize_results(self) -> dict[str, Any]:
        """Combine all teammate results into a final summary."""
        completed_tasks = self.shared_task_list.get_completed_tasks()
        timeline = self.progress_file.get_timeline()
        attack_path = self.knowledge_graph.get_attack_path()

        # Ask Brain to synthesize
        prompt = f"""Synthesize pentest results:

Completed Tasks: {json.dumps([t.get('description', '') for t in completed_tasks[:20]], indent=2)}
Attack Path: {json.dumps(attack_path, indent=2)}

Generate:
1. Executive summary (2-3 sentences)
2. Critical findings list
3. Recommendations"""

        try:
            synthesis = await self.client.call_brain(prompt, temperature=0.3)
        except Exception as e:
            synthesis = f"Synthesis failed: {e}"

        elapsed = time.monotonic() - self._start_time

        return {
            "executive_summary": synthesis,
            "completed_tasks": completed_tasks,
            "attack_path": attack_path,
            "timeline": timeline,
            "stats": {
                "total_tasks": len(completed_tasks),
                "elapsed_seconds": elapsed,
                "model_stats": self.model_alloy_router.get_stats(),
            },
        }

    # ═══════════════════════════════════════════════════════════════════════
    # CLEANUP
    # ═══════════════════════════════════════════════════════════════════════

    async def cleanup(self):
        """Terminate all teammates and clean up."""
        logger.info("Starting cleanup...")

        # Send termination signals
        for teammate in self.teammates:
            self.mailbox.send("team_lead", teammate["id"], {"type": "terminate"})

        # Wait for graceful shutdown (max 10s)
        tasks = [t["task"] for t in self.teammates if not t["task"].done()]
        if tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True), timeout=10
                )
            except asyncio.TimeoutError:
                logger.warning("Some teammates didn't finish gracefully")

        # Archive progress
        self.progress_file.archive()

        # Export knowledge graph
        if hasattr(self.knowledge_graph, 'export'):
            export_path = self.progress_file.working_dir
            if export_path:
                self.knowledge_graph.export(
                    os.path.join(export_path, "knowledge_graph.json")
                )

        # Clean locks
        self.lock_manager.cleanup()

        logger.info("Cleanup complete")
