"""Final test — Brain + Hands (arcee-ai/trinity-large-preview:free)."""
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

API_KEY = "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"

async def main():
    from redclaw.router.openrouter_client import OpenRouterClient

    client = OpenRouterClient(api_key=API_KEY)
    print(f"Brain: {client.BRAIN.model_id}")
    print(f"Hands: {client.HANDS.model_id}")
    print()

    # Test 1: Brain
    print("[1/3] Brain...", flush=True)
    try:
        r = await client.call_brain("Say exactly: BRAIN_OK", temperature=0.0)
        print(f"  PASS: {repr(r[:100])}", flush=True)
    except Exception as e:
        print(f"  FAIL: {e}", flush=True)

    await asyncio.sleep(5)

    # Test 2: Hands
    print("[2/3] Hands...", flush=True)
    try:
        r = await client.call_hands("Say exactly: HANDS_OK", temperature=0.0)
        print(f"  PASS: {repr(r[:100])}", flush=True)
    except Exception as e:
        print(f"  FAIL: {e}", flush=True)

    await asyncio.sleep(5)

    # Test 3: Dual Brain
    print("[3/3] Dual Brain collaboration...", flush=True)
    try:
        result = await client.dual_brain("Write a Python function to check if port 80 is open on a given IP")
        plan_ok = len(result.get("plan", "")) > 10
        code_ok = len(result.get("code", "")) > 10
        print(f"  Plan: {repr(result['plan'][:80])}", flush=True)
        print(f"  Code: {repr(result['code'][:80])}", flush=True)
        print(f"  {'PASS' if plan_ok and code_ok else 'FAIL'}", flush=True)
    except Exception as e:
        print(f"  FAIL: {e}", flush=True)

    stats = client.get_stats()
    print(f"\nStats: brain={stats['brain_calls']}, hands={stats['hands_calls']}, "
          f"errors={stats['errors']}, avg_latency={stats['avg_latency']:.2f}s")
    print("ALL DONE")

asyncio.run(main())
