"""
RedClaw V3.1 - Cross-Platform Test Suite (Windows + Linux)
Tests all imports, components, and live API.
"""
import asyncio
import json
import os
import sys
import tempfile
import shutil
import traceback

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

PASS = "PASS"
FAIL = "FAIL"
results = []

def log_result(test_name, passed, detail=""):
    results.append((test_name, passed, detail))
    s = "PASS" if passed else "FAIL"
    msg = f"  [{s}] {test_name}"
    if detail:
        msg += f" -- {detail}"
    print(msg, flush=True)


# ============================================================
print("=" * 60)
print("TEST 1: Module Imports")
print("=" * 60)

try:
    from redclaw import __version__
    log_result("redclaw version", __version__ == "3.1.0", f"v{__version__}")
except Exception as e:
    log_result("redclaw version", False, str(e))

modules = [
    ("redclaw.router.openrouter_client", "OpenRouterClient, LLMResponse, ModelProfile, TaskType, RateLimiter"),
    ("redclaw.router.model_alloy", "ModelAlloyRouter, ModelSelector, BalancedRouter, ModelPerformanceTracker"),
    ("redclaw.agents.shared_task_list", "SharedTaskList, TaskStatus"),
    ("redclaw.agents.mailbox", "Mailbox"),
    ("redclaw.agents.lock_manager", "LockManager"),
    ("redclaw.agents.team_lead", "TeamLead"),
    ("redclaw.agents.validator", "ValidatorAgent"),
    ("redclaw.agents.binary_analyst", "BinaryAnalystAgent, ZeroDayDetector"),
    ("redclaw.memory.memagent", "MemAgent"),
    ("redclaw.memory.knowledge_graph", "PentestKnowledgeGraph, get_knowledge_graph"),
    ("redclaw.memory.memory_rag", "MemoryRAG"),
    ("redclaw.reporting.causal_chain", "CausalChainReport"),
]

for mod_name, classes in modules:
    try:
        __import__(mod_name)
        log_result(f"import {mod_name}", True)
    except Exception as e:
        log_result(f"import {mod_name}", False, str(e))

from redclaw.router.openrouter_client import OpenRouterClient, ModelProfile
from redclaw.router.model_alloy import ModelSelector, BalancedRouter, ModelPerformanceTracker
from redclaw.agents.shared_task_list import SharedTaskList
from redclaw.agents.mailbox import Mailbox
from redclaw.agents.lock_manager import LockManager
from redclaw.memory.memagent import MemAgent
from redclaw.memory.knowledge_graph import PentestKnowledgeGraph
from redclaw.memory.memory_rag import MemoryRAG
from redclaw.agents.binary_analyst import ZeroDayDetector
from redclaw.reporting.causal_chain import CausalChainReport

# ============================================================
print("\n" + "=" * 60)
print("TEST 2: OpenRouter Client Config")
print("=" * 60)

client = OpenRouterClient(api_key="test-key")
log_result("Brain model ID", client.BRAIN.model_id == "openai/gpt-oss-120b:free", client.BRAIN.model_id)
log_result("Hands model ID", client.HANDS.model_id == "arcee-ai/trinity-large-preview:free", client.HANDS.model_id)
log_result("Base URL", "openrouter.ai" in client.base_url)

# ============================================================
print("\n" + "=" * 60)
print("TEST 3: Model Alloy")
print("=" * 60)

selector = ModelSelector()
brain_task = selector.classify_task("Analyze the nmap results and evaluate risk")
log_result("Brain classification", brain_task == "openai/gpt-oss-120b:free", brain_task)

router = BalancedRouter()
for i in range(10):
    router.route({"description": "analyze plan strategy" if i < 5 else "write code implement"})
stats = router.get_stats()
log_result("Router balance", abs(stats["brain_ratio"] - 0.6) < 0.2, f"ratio={stats['brain_ratio']:.2f}")

# ============================================================
print("\n" + "=" * 60)
print("TEST 4: SharedTaskList (cross-platform SQLite)")
print("=" * 60)

tmp = tempfile.mkdtemp()
try:
    stl = SharedTaskList(db_path=os.path.join(tmp, "tasks.db"))
    stl.add_task("s1", "Nmap scan", [], 10)
    stl.add_task("s2", "Nuclei scan", [], 5)
    stl.add_task("e1", "Exploit", ["s1"])
    t = stl.claim_task("a1")
    log_result("Claim highest priority", t and t["task_id"] == "s1")
    t2 = stl.claim_task("a2")
    log_result("Dependency blocks", t2 and t2["task_id"] == "s2")
    stl.complete_task("s1", '{"ok":1}')
    stl.complete_task("s2", '{"ok":1}')
    t3 = stl.claim_task("a3")
    log_result("Dependency resolved", t3 and t3["task_id"] == "e1")
    stl.complete_task("e1", '{"ok":1}')
    log_result("All complete", stl.all_tasks_complete())
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ============================================================
print("\n" + "=" * 60)
print("TEST 5: Mailbox (cross-platform SQLite)")
print("=" * 60)

tmp = tempfile.mkdtemp()
try:
    mb = Mailbox(db_path=os.path.join(tmp, "mail.db"))
    mb.register_agent("lead")
    mb.register_agent("a1")
    mb.register_agent("a2")
    mb.send("a1", "lead", {"type": "done"})
    log_result("Has messages", mb.has_messages("lead"))
    msgs = mb.get_messages("lead")
    log_result("Get messages", len(msgs) == 1)
    log_result("Read clears", not mb.has_messages("lead"))
    mb.broadcast("lead", {"type": "alert"})
    log_result("Broadcast", mb.has_messages("a1") and mb.has_messages("a2"))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ============================================================
print("\n" + "=" * 60)
print("TEST 6: LockManager (cross-platform file locks)")
print("=" * 60)

tmp = tempfile.mkdtemp()
try:
    lm = LockManager(lock_dir=os.path.join(tmp, "locks"))
    log_result("Acquire", lm.acquire("res1", "a1"))
    log_result("Is locked", lm.is_locked("res1"))
    log_result("Owner check", lm.get_lock_owner("res1") == "a1")
    log_result("Block other", not lm.acquire("res1", "a2", timeout=0))
    log_result("Release", lm.release("res1", "a1"))
    log_result("Unlocked", not lm.is_locked("res1"))
    lm.cleanup()
    log_result("Cleanup", True)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ============================================================
print("\n" + "=" * 60)
print("TEST 7: MemAgent (cross-platform file I/O)")
print("=" * 60)

tmp = tempfile.mkdtemp()
try:
    mem = MemAgent(working_dir=tmp)
    mem.initialize("Test pentest")
    log_result("Init", mem._state["current_status"] == "PLANNING")
    mem.add_pending_tasks([{"id": "t1", "description": "Scan"}])
    log_result("Add task", len(mem._state["pending_tasks"]) == 1)
    mem.update_task_status("t1", "COMPLETE", "Done")
    log_result("Complete task", len(mem._state["completed_tasks"]) == 1)
    mem.add_finding("CVE-2021-41773", "critical")
    log_result("Add finding", len(mem._state["key_findings"]) == 1)
    log_result("Progress file", os.path.exists(os.path.join(tmp, "claude-progress.txt")))
    log_result("JSON file", os.path.exists(os.path.join(tmp, "claude-progress.txt.json")))
    # Test cross-platform paths
    log_result("Path separator", os.sep in os.path.join(tmp, "claude-progress.txt"))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ============================================================
print("\n" + "=" * 60)
print("TEST 8: KnowledgeGraph")
print("=" * 60)

g = PentestKnowledgeGraph()
g.add_host("10.0.0.1", os="Linux")
g.add_port("10.0.0.1", 80, "open")
g.add_service("10.0.0.1", 80, "Apache", "2.4.49")
g.add_vulnerability("10.0.0.1:80:Apache", "CVE-2021-41773", "critical", 9.8)
stats = g.get_stats()
log_result("Graph nodes", stats["total_nodes"] == 4, f"n={stats['total_nodes']}")
vulns = g.get_vulnerabilities_for_host("10.0.0.1")
log_result("Query vulns", vulns["count"] == 1)
nl = g.query_natural_language("Find vulnerabilities on 10.0.0.1")
log_result("NL query", nl.get("count") == 1)

# ============================================================
print("\n" + "=" * 60)
print("TEST 9: MemoryRAG (in-memory fallback)")
print("=" * 60)

async def test_rag():
    tmp = tempfile.mkdtemp()
    try:
        rag = MemoryRAG(persist_directory=tmp)
        await rag.ingest_cve("CVE-2021-41773", "Apache path traversal", cvss_score=9.8)
        cves = await rag.query_cve("Apache", "2.4.49")
        log_result("CVE ingest+query", len(cves) >= 1)
        await rag.store_successful_exploit({"service": "Apache", "version": "2.4.49", "cve": "CVE-2021-41773"})
        past = await rag.query_past_exploits("Apache", "2.4.49")
        log_result("Exploit store+query", len(past) >= 1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
asyncio.run(test_rag())

# ============================================================
print("\n" + "=" * 60)
print("TEST 10: ZeroDayDetector")
print("=" * 60)

det = ZeroDayDetector()
code = 'void f(char *x){char b[64];strcpy(b,x);printf(x);char *p="admin123";}'
findings = det.scan(code)
types = set(f["type"] for f in findings)
log_result("Buffer overflow", "buffer_overflow" in types)
log_result("Format string", "format_string" in types)
log_result("Hardcoded creds", "hardcoded_creds" in types)

# ============================================================
print("\n" + "=" * 60)
print("TEST 11: CausalChainReport")
print("=" * 60)

tmp = tempfile.mkdtemp()
try:
    rep = CausalChainReport(output_dir=tmp)
    finding = {"id": 1, "title": "Test", "cve": "CVE-2021-41773", "cvss": 9.8,
               "service": "Apache", "impact": "RCE", "root_cause": "Path traversal",
               "steps": ["Found Apache", "Exploited"], "target": {"os": "Linux", "software": "Apache"}}
    txt = rep.generate(finding, {"validated": True, "proof": {"http_status": "200"}})
    log_result("Report format", "WHY" in txt and "WHAT" in txt and "HOW" in txt and "FIX" in txt)
    full = rep.generate_full_report({"completed_tasks": [finding], "executive_summary": "Test", "attack_path": {}}, "Test")
    log_result("Full report", len(full["text"]) > 100)
    path = rep.export_text(full)
    log_result("Export text", os.path.exists(path))
    # Cross-platform path check
    log_result("Export path valid", os.sep in path or "/" in path)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ============================================================
print("\n" + "=" * 60)
print("TEST 12: Cross-Platform Path Checks")
print("=" * 60)

log_result("tempdir exists", os.path.isdir(tempfile.gettempdir()))
log_result("home expanduser", os.path.isdir(os.path.expanduser("~")))
log_result("redclaw dir expandable", len(os.path.expanduser("~/.redclaw")) > 5)
log_result("os.sep correct", os.sep == "\\" if sys.platform == "win32" else os.sep == "/")
log_result("platform", True, sys.platform)

# ============================================================
print("\n" + "=" * 60)
print("TEST 13: LIVE OpenRouter API")
print("=" * 60)

API_KEY = "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"

async def test_api():
    client = OpenRouterClient(api_key=API_KEY)
    # Brain
    print("  Calling Brain...", flush=True)
    try:
        r = await client.call_brain("Say exactly: BRAIN_OK", temperature=0.0)
        log_result("Brain API", "BRAIN" in r.upper() or "OK" in r.upper(), repr(r[:60]))
    except Exception as e:
        log_result("Brain API", False, str(e)[:80])

    await asyncio.sleep(10)

    # Hands
    print("  Calling Hands...", flush=True)
    try:
        r = await client.call_hands("Say exactly: HANDS_OK", temperature=0.0)
        log_result("Hands API", len(r) > 0, repr(r[:60]))
    except Exception as e:
        log_result("Hands API", False, str(e)[:80])

asyncio.run(test_api())

# ============================================================
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)

total = len(results)
passed = sum(1 for _, p, _ in results if p)
failed = sum(1 for _, p, _ in results if not p)

print(f"\n  Total:  {total}")
print(f"  Passed: {passed}")
print(f"  Failed: {failed}")
print(f"  Rate:   {passed/total*100:.1f}%\n")

if failed > 0:
    print("Failed tests:")
    for name, p, detail in results:
        if not p:
            print(f"  [FAIL] {name}: {detail}")
print()
