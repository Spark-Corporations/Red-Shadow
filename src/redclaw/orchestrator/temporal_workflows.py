"""
Temporal Workflows — Parallel pentest execution for RedClaw V3.1

Workflows:
  - ReconWorkflow: Parallel nmap + nuclei + dirb
  - FullPentestWorkflow: Recon -> Assessment -> Exploitation

Falls back to asyncio.gather when Temporal server is unavailable.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Dict, List

logger = logging.getLogger("redclaw.orchestrator.temporal_workflows")

# Try to import Temporal, fall back gracefully
try:
    from temporalio import workflow
    HAS_TEMPORAL = True
except ImportError:
    HAS_TEMPORAL = False
    logger.info("Temporal not installed. Using asyncio fallback. Install with: pip install temporalio")


# ── Asyncio Fallback Workflows ────────────────────────────────────────────────
# Used when Temporal server is not available

class AsyncReconWorkflow:
    """Parallel reconnaissance using asyncio (Temporal fallback)."""

    def __init__(self, activities):
        self.activities = activities

    async def run(self, target: str) -> Dict[str, Any]:
        """Execute parallel reconnaissance."""
        logger.info(f"Running AsyncReconWorkflow for {target}")

        # Run all recon activities in parallel
        tasks = [
            self.activities.run_nmap(target),
            self.activities.run_nuclei(target),
            self.activities.run_dirb(f"http://{target}"),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        nmap_result = results[0] if not isinstance(results[0], Exception) else {"error": str(results[0])}
        nuclei_result = results[1] if not isinstance(results[1], Exception) else {"error": str(results[1])}
        dirb_result = results[2] if not isinstance(results[2], Exception) else {"error": str(results[2])}

        # Ingest to knowledge graph
        await self.activities.ingest_to_graph({
            "target": target,
            "results": [nmap_result, nuclei_result, dirb_result],
        })

        return {
            "phase": "recon_complete",
            "target": target,
            "nmap_ports": len(nmap_result.get("open_ports", [])) if isinstance(nmap_result, dict) else 0,
            "nuclei_vulns": len(nuclei_result.get("vulnerabilities", [])) if isinstance(nuclei_result, dict) else 0,
            "dirb_paths": len(dirb_result.get("paths", [])) if isinstance(dirb_result, dict) else 0,
        }


class AsyncFullPentestWorkflow:
    """Complete pentest workflow using asyncio (Temporal fallback)."""

    def __init__(self, activities):
        self.activities = activities

    async def run(self, target: str) -> Dict[str, Any]:
        """Execute full pentest pipeline."""
        logger.info(f"Running AsyncFullPentestWorkflow for {target}")

        # Phase 1: Recon
        recon = AsyncReconWorkflow(self.activities)
        recon_result = await recon.run(target)
        logger.info(f"Recon complete: {recon_result}")

        # Phase 2: Query graph for vulnerabilities
        vulns = await self.activities.query_knowledge_graph(
            f"Find all vulnerabilities on {target}"
        )

        return {
            "target": target,
            "phases_complete": ["recon", "assessment"],
            "recon_summary": recon_result,
            "vulnerabilities_found": len(vulns.get("vulnerabilities", [])) if isinstance(vulns, dict) else 0,
        }


# ── Temporal Workflows ────────────────────────────────────────────────────────

if HAS_TEMPORAL:
    from .activities import (
        run_nmap_activity,
        run_nuclei_activity,
        run_dirb_activity,
        ingest_to_graph_activity,
        query_knowledge_graph_activity,
    )

    @workflow.defn
    class ReconWorkflow:
        """Parallel reconnaissance workflow (Temporal-managed)."""

        @workflow.run
        async def run(self, target: str) -> Dict[str, Any]:
            # Parallel recon tasks
            recon_tasks = [
                workflow.execute_activity(
                    run_nmap_activity, target,
                    start_to_close_timeout=timedelta(minutes=30),
                ),
                workflow.execute_activity(
                    run_nuclei_activity, target,
                    start_to_close_timeout=timedelta(minutes=20),
                ),
                workflow.execute_activity(
                    run_dirb_activity, f"http://{target}",
                    start_to_close_timeout=timedelta(minutes=15),
                ),
            ]

            results = await asyncio.gather(*recon_tasks)

            # Ingest to Knowledge Graph
            await workflow.execute_activity(
                ingest_to_graph_activity,
                {"target": target, "results": results},
                start_to_close_timeout=timedelta(minutes=5),
            )

            return {
                "phase": "recon_complete",
                "target": target,
                "nmap_ports": len(results[0].get("open_ports", [])),
                "nuclei_vulns": len(results[1].get("vulnerabilities", [])),
                "dirb_paths": len(results[2].get("paths", [])),
            }


    @workflow.defn
    class FullPentestWorkflow:
        """Complete pentest workflow (Temporal-managed)."""

        @workflow.run
        async def run(self, target: str) -> Dict[str, Any]:
            # Phase 1: Recon
            recon_result = await workflow.execute_child_workflow(
                ReconWorkflow.run, target, id=f"recon-{target}"
            )

            # Phase 2: Assessment
            vulns = await workflow.execute_activity(
                query_knowledge_graph_activity,
                f"Find all vulnerabilities on {target}",
                start_to_close_timeout=timedelta(seconds=30),
            )

            return {
                "target": target,
                "phases_complete": ["recon", "assessment"],
                "vulnerabilities_found": len(vulns.get("vulnerabilities", [])),
            }


# ── Factory Function ──────────────────────────────────────────────────────────


def get_recon_workflow(activities=None):
    """Get the appropriate recon workflow based on Temporal availability."""
    if HAS_TEMPORAL:
        return ReconWorkflow
    else:
        return AsyncReconWorkflow(activities)


def get_full_pentest_workflow(activities=None):
    """Get the appropriate full pentest workflow."""
    if HAS_TEMPORAL:
        return FullPentestWorkflow
    else:
        return AsyncFullPentestWorkflow(activities)
