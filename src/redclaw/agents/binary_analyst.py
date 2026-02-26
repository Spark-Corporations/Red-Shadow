"""
BinaryAnalystAgent — Binary analysis using Ghidra, Radare2, and pattern detection.

Analyzes compiled binaries for:
  - Buffer overflows
  - Format string vulnerabilities
  - Integer overflows
  - Use-after-free conditions
  - Hardcoded credentials

Uses LLM to interpret analysis results and prioritize findings.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("redclaw.agents.binary_analyst")


class ZeroDayDetector:
    """
    Pattern-matching engine for binary vulnerability detection.

    Searches decompiled/disassembled code for common vulnerability patterns.
    """

    PATTERNS = {
        "buffer_overflow": {
            "indicators": [
                r"strcpy\s*\(",
                r"strcat\s*\(",
                r"sprintf\s*\(",
                r"gets\s*\(",
                r"scanf\s*\(\s*\"%s\"",
                r"memcpy\s*\([^,]+,\s*[^,]+,\s*[^)]*user",
            ],
            "severity": "critical",
            "description": "Potential buffer overflow via unsafe string/memory function",
        },
        "format_string": {
            "indicators": [
                r"printf\s*\(\s*[a-zA-Z_]+\s*\)",
                r"fprintf\s*\([^,]+,\s*[a-zA-Z_]+\s*\)",
                r"sprintf\s*\([^,]+,\s*[a-zA-Z_]+\s*\)",
                r"syslog\s*\([^,]+,\s*[a-zA-Z_]+\s*\)",
            ],
            "severity": "high",
            "description": "Format string vulnerability — user input used as format specifier",
        },
        "integer_overflow": {
            "indicators": [
                r"malloc\s*\(\s*[a-zA-Z_]+\s*\*\s*[a-zA-Z_]+\s*\)",
                r"\(\s*unsigned\s*(int|short|char)\s*\)\s*[a-zA-Z_]+",
                r"size\s*=\s*[a-zA-Z_]+\s*\+\s*\d+",
            ],
            "severity": "high",
            "description": "Potential integer overflow in size calculation",
        },
        "use_after_free": {
            "indicators": [
                r"free\s*\(\s*([a-zA-Z_]+)\s*\)[\s\S]{0,100}\1",
                r"delete\s+([a-zA-Z_]+)[\s\S]{0,100}\1->",
            ],
            "severity": "critical",
            "description": "Use-after-free — memory accessed after deallocation",
        },
        "hardcoded_creds": {
            "indicators": [
                r"password\s*=\s*\"[^\"]+\"",
                r"passwd\s*=\s*\"[^\"]+\"",
                r"api_key\s*=\s*\"[^\"]+\"",
                r"secret\s*=\s*\"[^\"]+\"",
            ],
            "severity": "medium",
            "description": "Hardcoded credentials found in binary",
        },
    }

    def scan(self, code: str) -> List[Dict[str, Any]]:
        """
        Scan decompiled code for vulnerability patterns.

        Args:
            code: Decompiled/disassembled source code

        Returns:
            List of detected vulnerability patterns
        """
        findings = []

        for vuln_type, pattern_info in self.PATTERNS.items():
            for indicator in pattern_info["indicators"]:
                matches = re.finditer(indicator, code, re.IGNORECASE)
                for match in matches:
                    # Get surrounding context (5 lines before/after)
                    start = max(0, code.rfind("\n", 0, match.start()) - 200)
                    end = min(len(code), code.find("\n", match.end()) + 200)
                    context = code[start:end].strip()

                    findings.append({
                        "type": vuln_type,
                        "severity": pattern_info["severity"],
                        "description": pattern_info["description"],
                        "match": match.group(0),
                        "position": match.start(),
                        "context": context[:300],
                        "pattern": indicator,
                    })

        return findings


class BinaryAnalystAgent:
    """
    Binary analysis agent using Ghidra, Radare2, and pattern detection.

    Usage:
        from redclaw.router import OpenRouterClient

        client = OpenRouterClient()
        analyst = BinaryAnalystAgent(client)

        results = await analyst.analyze_binary("/path/to/binary")
    """

    def __init__(self, client, working_dir: Optional[str] = None):
        self.client = client
        self.working_dir = working_dir
        self.zero_day_detector = ZeroDayDetector()

    async def analyze_binary(self, binary_path: str) -> Dict[str, Any]:
        """
        Full binary analysis pipeline.

        1. Decompile with Ghidra (headless)
        2. Disassemble with Radare2
        3. Pattern matching for known vulnerability types
        4. LLM analysis of findings
        """
        analysis_id = f"bin_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        logger.info(f"Starting binary analysis {analysis_id}: {binary_path}")

        results = {
            "analysis_id": analysis_id,
            "binary": binary_path,
            "timestamp": datetime.now().isoformat(),
            "findings": [],
        }

        # Step 1: Decompile (generates pseudo-C code)
        decompiled = await self._decompile_ghidra(binary_path)

        # Step 2: Disassemble (generates assembly)
        disassembly = await self._disassemble_radare2(binary_path)

        # Step 3: Pattern matching on decompiled code
        if decompiled:
            patterns = self.zero_day_detector.scan(decompiled)
            results["pattern_findings"] = patterns
            results["findings"].extend(patterns)
            logger.info(f"Pattern scan: {len(patterns)} potential vulnerabilities")

        # Step 4: LLM deep analysis
        llm_findings = await self._llm_analyze(binary_path, decompiled, disassembly, results["findings"])
        results["llm_analysis"] = llm_findings

        # Summary
        critical_count = sum(1 for f in results["findings"] if f.get("severity") == "critical")
        results["summary"] = {
            "total_findings": len(results["findings"]),
            "critical": critical_count,
            "high": sum(1 for f in results["findings"] if f.get("severity") == "high"),
            "medium": sum(1 for f in results["findings"] if f.get("severity") == "medium"),
        }

        logger.info(f"Binary analysis complete: {len(results['findings'])} findings ({critical_count} critical)")
        return results

    async def _decompile_ghidra(self, binary_path: str) -> str:
        """Decompile binary using Ghidra headless mode."""
        # In production:
        # analyzeHeadless <tempdir>/ghidra_project . -import {binary_path} -postScript ExportDecompiled.py
        logger.info(f"Decompiling with Ghidra: {binary_path}")

        # For now, return placeholder text indicating Ghidra integration point
        return f"// Ghidra decompilation of {binary_path}\n// TODO: Integrate Ghidra headless analyzer"

    async def _disassemble_radare2(self, binary_path: str) -> str:
        """Disassemble binary using Radare2."""
        # In production:
        # r2 -q -c "aaa; pdf @@ sym.*" {binary_path}
        logger.info(f"Disassembling with Radare2: {binary_path}")

        return f"; Radare2 disassembly of {binary_path}\n; TODO: Integrate r2pipe"

    async def _llm_analyze(
        self, binary_path: str, decompiled: str, disassembly: str,
        pattern_findings: List[Dict]
    ) -> str:
        """Use LLM to analyze findings and provide expert assessment."""
        try:
            findings_summary = json.dumps(pattern_findings[:10], indent=2) if pattern_findings else "No patterns found"

            analysis = await self.client.call_brain(
                prompt=f"""Analyze these binary analysis results:

Binary: {binary_path}
Pattern Findings: {findings_summary}

Decompiled Code (excerpt):
{decompiled[:1000]}

Provide:
1. Risk assessment for each finding
2. Exploitability rating (Easy/Medium/Hard)
3. Recommended exploitation approach
4. Potential zero-day indicators""",
                temperature=0.4,
            )
            return analysis

        except Exception as e:
            return f"LLM analysis failed: {e}"
