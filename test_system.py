"""
RedClaw Quick Test — Verify API connectivity + core modules.

Tests:
  1. API key loaded correctly
  2. LLM endpoint reachable (glm-5 via DashScope)
  3. Core module imports work
  4. KnowledgeGraph + Memory initialize
  5. Full pentest object creation

Usage:
  # Set env vars first, then run:
  $env:REDCLAW_LLM_URL = "https://coding-intl.dashscope.aliyuncs.com/v1"
  $env:REDCLAW_LLM_MODEL = "glm-5"
  python test_system.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

PASSED = FAILED = 0

def test(name, cond, detail=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  ✅ {name}" + (f" — {detail}" if detail else ""))
    else:
        FAILED += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


async def main():
    global PASSED, FAILED

    print("=" * 60)
    print("  🔴 RedClaw v3.1 — System Test")
    print("=" * 60)

    # ── Test 1: API Key ──
    print("\n🔑 Test 1: API Key")
    from pathlib import Path
    key_file = Path.home() / ".redclaw" / "api_key.txt"
    key_exists = key_file.exists()
    test("~/.redclaw/api_key.txt exists", key_exists)
    if key_exists:
        key = key_file.read_text().strip()
        test("Key is not empty", len(key) > 0, f"{len(key)} chars")
        test("Key starts with sk-", key.startswith("sk-"), key[:10] + "...")
    else:
        FAILED += 2
        print("  ❌ Key file missing!")

    # ── Test 2: Environment Variables ──
    print("\n🌐 Test 2: Environment Variables")
    llm_url = os.environ.get("REDCLAW_LLM_URL", "(not set)")
    llm_model = os.environ.get("REDCLAW_LLM_MODEL", "(not set)")
    test("REDCLAW_LLM_URL set", llm_url != "(not set)", llm_url)
    test("REDCLAW_LLM_MODEL set", llm_model != "(not set)", llm_model)
    if llm_url == "(not set)":
        print("    ⚠️  Will fallback to default: https://openrouter.ai/api/v1")
    if llm_model == "(not set)":
        print("    ⚠️  Will fallback to default: openai/gpt-4.1-mini")

    # ── Test 3: Core Imports ──
    print("\n📦 Test 3: Core Module Imports")
    modules = [
        ("redclaw.pentest", "RedClawPentest"),
        ("redclaw.openclaw_bridge.runtime", "OpenClawRuntime"),
        ("redclaw.openclaw_bridge.runtime", "RuntimeConfig"),
        ("redclaw.openclaw_bridge.knowledge_graph", "PentestKnowledgeGraph"),
        ("redclaw.openclaw_bridge.hypothesis_engine", "HypothesisEngine"),
        ("redclaw.openclaw_bridge.exploit_phase_agent", "ExploitPhaseAgent"),
        ("redclaw.openclaw_bridge.post_exploit_chain", "PostExploitChain"),
        ("redclaw.openclaw_bridge.adaptive_mutation", "ExploitLoop"),
    ]
    for mod_path, cls_name in modules:
        try:
            mod = __import__(mod_path, fromlist=[cls_name])
            cls = getattr(mod, cls_name)
            test(f"{cls_name}", True)
        except Exception as e:
            test(f"{cls_name}", False, str(e)[:80])

    # ── Test 4: RuntimeConfig ──
    print("\n⚙️  Test 4: RuntimeConfig Loading")
    from redclaw.openclaw_bridge.runtime import RuntimeConfig
    config = RuntimeConfig()
    test("Endpoint loaded", bool(config.llm_endpoint), config.llm_endpoint)
    test("Model loaded", bool(config.llm_model), config.llm_model)
    test("API key loaded", bool(config.llm_api_key), 
         f"{config.llm_api_key[:10]}..." if config.llm_api_key else "MISSING!")

    # ── Test 5: KnowledgeGraph ──
    print("\n🧠 Test 5: KnowledgeGraph")
    try:
        from redclaw.openclaw_bridge.knowledge_graph import PentestKnowledgeGraph
        kg = PentestKnowledgeGraph()
        stats = kg.get_stats()
        test("KG initialized", True, f"{stats['total_nodes']} nodes")
    except Exception as e:
        test("KG initialized", False, str(e)[:80])

    # ── Test 6: LLM API Call ──
    print("\n🤖 Test 6: LLM API Call (glm-5)")
    try:
        import aiohttp

        api_key = config.llm_api_key
        endpoint = config.llm_endpoint.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        model = config.llm_model

        print(f"    Endpoint: {endpoint}")
        print(f"    Model:    {model}")
        print(f"    Key:      {api_key[:10]}...")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Reply with just 'ok'"}],
            "temperature": 0.1,
            "max_tokens": 10,
        }

        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(endpoint, headers=headers, json=payload) as resp:
                status = resp.status
                body = await resp.text()

                test("HTTP status 200", status == 200, f"got {status}")

                if status == 200:
                    import json
                    data = json.loads(body)
                    content = data["choices"][0]["message"]["content"]
                    model_used = data.get("model", "unknown")
                    usage = data.get("usage", {})
                    test("Response has content", bool(content), f'"{content}"')
                    test("Model confirmed", bool(model_used), model_used)
                    tokens = usage.get("total_tokens", 0)
                    if tokens:
                        test("Token usage reported", True, f"{tokens} tokens")
                else:
                    print(f"    Response: {body[:300]}")
                    test("API error", False, body[:200])

    except Exception as e:
        test("LLM API call", False, str(e)[:200])

    # ── Test 7: Pentest Object Creation ──
    print("\n🎯 Test 7: RedClawPentest Object")
    try:
        from redclaw.pentest import RedClawPentest
        p = RedClawPentest(
            target="127.0.0.1",
            api_key=config.llm_api_key or "test-key",
        )
        test("Object created", True)
        test("Target set", p.target == "127.0.0.1")
        test("LLM model set", bool(p.llm_model), p.llm_model)
        test("LLM endpoint set", bool(p.llm_endpoint), p.llm_endpoint[:50])
    except Exception as e:
        test("Object creation", False, str(e)[:80])

    # ── Summary ──
    print(f"\n{'=' * 60}")
    print(f"  Results: {PASSED} passed, {FAILED} failed, {PASSED + FAILED} total")
    if FAILED == 0:
        print("  🎉 ALL SYSTEMS OPERATIONAL")
    else:
        print(f"  ⚠️  {FAILED} issues found — check above")
    print("=" * 60)

    return FAILED == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
