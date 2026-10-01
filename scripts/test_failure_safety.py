#!/usr/bin/env python3
"""Offline unit test: proves fetch failure and filter mismatch never clobber state file.

Assertions:
1. Network fetch failure returns 1 and leaves state file byte-identical.
2. Filter mismatch with --commit returns 1 and leaves state file byte-identical.
3. Filter mismatch with --commit --force successfully updates state file.
"""
import hashlib
import importlib.util
import json
import os
import sys
import tempfile

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "fetch_and_diff.py")
spec = importlib.util.spec_from_file_location("fad", SCRIPT)
fad = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fad)

SAMPLE_DATA = {
    "generatedAt": "2026-09-30",
    "points": [
        {
            "id": "x::y",
            "plan": "Plan X",
            "vendor": "VendorX",
            "billing": "subscription",
            "model": "y",
            "currency": "USD",
            "local_price": None,
            "price_usd": 20,
            "real_usd_per_mtok": 0.03,
            "promo_until": None,
            "unmetered": False,
            "confidence": "high",
        },
        {
            "id": "z::w",
            "plan": "Plan Z",
            "vendor": "VendorZ",
            "billing": "subscription",
            "model": "w",
            "currency": "USD",
            "local_price": None,
            "price_usd": 30,
            "real_usd_per_mtok": 0.04,
            "promo_until": None,
            "unmetered": False,
            "confidence": "medium",
        },
    ],
}


def test_fetch_failure():
    def boom(path):
        raise RuntimeError("simulated network failure")

    fad.fetch_json = boom
    d = tempfile.mkdtemp()
    state = os.path.join(d, "state.json")
    good = {"generatedAt": "2026-09-30", "count": 1,
            "rows": {"x::y": {"plan": "P", "vendor": "V", "billing": "subscription",
                              "model": "y", "currency": "USD", "local_price": None,
                              "w": {"price_usd": 20, "real_usd_per_mtok": 0.03,
                                    "promo_until": None, "unmetered": False,
                                    "confidence": "high"}}}}
    with open(state, "w") as f:
        json.dump(good, f)
    before = hashlib.md5(open(state, "rb").read()).hexdigest()

    sys.argv = ["fad", "--state", state, "--commit"]
    rc = fad.main()
    after = hashlib.md5(open(state, "rb").read()).hexdigest()
    ok = (rc == 1) and (before == after)
    print("[TEST 1: fetch failure] rc=%d, state_untouched=%s -> %s"
          % (rc, before == after, "PASS" if ok else "FAIL"))
    return ok


def test_filter_mismatch_refusal():
    fad.fetch_json = lambda path: SAMPLE_DATA
    d = tempfile.mkdtemp()
    state = os.path.join(d, "state.json")
    existing_state = {
        "generatedAt": "2026-09-30",
        "filter": {"only": "subscription", "vendor": "VendorX", "plan_regex": None},
        "count": 1,
        "rows": {"x::y": {"plan": "Plan X", "vendor": "VendorX", "billing": "subscription",
                          "model": "y", "currency": "USD", "local_price": None,
                          "w": {"price_usd": 20, "real_usd_per_mtok": 0.03,
                                "promo_until": None, "unmetered": False,
                                "confidence": "high"}}},
    }
    with open(state, "w") as f:
        json.dump(existing_state, f)
    before = hashlib.md5(open(state, "rb").read()).hexdigest()

    # Try to commit with a different vendor without --force
    sys.argv = ["fad", "--state", state, "--vendor", "VendorZ", "--commit"]
    rc = fad.main()
    after = hashlib.md5(open(state, "rb").read()).hexdigest()
    ok = (rc == 1) and (before == after)
    print("[TEST 2: filter mismatch commit refusal] rc=%d, state_untouched=%s -> %s"
          % (rc, before == after, "PASS" if ok else "FAIL"))
    return ok


def test_filter_mismatch_force():
    fad.fetch_json = lambda path: SAMPLE_DATA
    d = tempfile.mkdtemp()
    state = os.path.join(d, "state.json")
    existing_state = {
        "generatedAt": "2026-09-30",
        "filter": {"only": "subscription", "vendor": "VendorX", "plan_regex": None},
        "count": 1,
        "rows": {},
    }
    with open(state, "w") as f:
        json.dump(existing_state, f)

    # Commit with --force
    sys.argv = ["fad", "--state", state, "--vendor", "VendorZ", "--commit", "--force"]
    rc = fad.main()
    with open(state) as f:
        updated = json.load(f)
    ok = (rc in (0, 2)) and (updated.get("filter", {}).get("vendor") == "VendorZ")
    print("[TEST 3: filter mismatch force commit] rc=%d, updated_filter=%s -> %s"
          % (rc, updated.get("filter", {}).get("vendor"), "PASS" if ok else "FAIL"))
    return ok


if __name__ == "__main__":
    results = [
        test_fetch_failure(),
        test_filter_mismatch_refusal(),
        test_filter_mismatch_force(),
    ]
    all_ok = all(results)
    print("\nOVERALL: %s" % ("ALL TESTS PASSED" if all_ok else "SOME TESTS FAILED"))
    sys.exit(0 if all_ok else 1)
