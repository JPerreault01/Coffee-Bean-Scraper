#!/usr/bin/env python3
"""
Validation tests for build_skill_knowledge.py.

Test 1 — Schema round-trip: build a stub skill_knowledge.json from fake digests,
  run assemble_skill.py logic against it, confirm no KeyError.

Test 2 — Tool-use parse: confirm block.input with quotes/apostrophes compiles
  cleanly, and json_repair fallback recovers broken JSON.

Test 3 — Dry-run: run --dry-run against actual training_data/cleaned/ if it exists.
"""

import json
import sys
import traceback
from pathlib import Path

# Add repo root to path
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "data_pipeline"))

# ---------------------------------------------------------------------------
# Test 1 — Schema round-trip against assemble_skill.py
# ---------------------------------------------------------------------------

def test_schema_round_trip() -> bool:
    """
    Build a minimal skill_knowledge.json with the exact schema our compiler
    produces, then exercise split_knowledge_to_files() from assemble_skill.py
    and confirm no KeyError or AttributeError.
    """
    print("\n=== Test 1: Schema round-trip ===")
    try:
        from assemble_skill import split_knowledge_to_files
    except ImportError as exc:
        print(f"  FAIL — could not import assemble_skill: {exc}")
        return False

    import tempfile
    import os

    # Build a minimal stub knowledge dict using our compiler's schema
    stub_knowledge = {
        "consensus_claims": [
            {"claim": "Light roasts have more acidity than dark roasts.", "category": "roast", "source": "src_001"},
            {"claim": "Espresso requires fine grind size.", "category": "espresso", "source": "src_002"},
        ],
        "contested_claims": [
            {"claim": "Single origin espresso is better than blends.", "category": "espresso", "source": "src_001"},
        ],
        "vocabulary": {
            "bloom": "The initial wetting of grounds to release CO2 before full extraction.",
            "channeling": "Uneven water flow through the puck causing extraction defects.",
            "ristretto": "A short, concentrated espresso shot with higher coffee-to-water ratio.",
        },
        "tasting_descriptors": [
            "blueberry", "caramel sweetness", "dark chocolate", "floral",
            "fruity brightness", "nuttiness", "stone fruit",
        ],
        "community_framing": [
            {
                "source": "src_001",
                "framing": "This community prioritizes extraction consistency and repeatability over exotic flavors.",
            },
            {
                "source": "src_002",
                "framing": "Focused on value: great coffee doesn't require expensive equipment.",
            },
        ],
        "key_insights": [
            {
                "insight": "Water temperature of 93-96C works for most filter brewing.",
                "category": "pour_over",
                "source": "src_001",
            },
            {
                "insight": "Pre-infusion reduces channeling risk significantly.",
                "category": "espresso",
                "source": "src_002",
            },
        ],
        "meta": {
            "total_sources": 2,
            "categories": ["espresso", "pour_over", "roast"],
            "per_source_type": {"reddit": 1, "web": 1},
            "per_category": {"espresso": 1, "roast": 1},
            "digest_model": "claude-sonnet-4-6",
            "build_timestamp": "2026-06-03T00:00:00+00:00",
            "total_consensus_claims": 2,
            "total_contested_claims": 1,
            "total_vocabulary_terms": 3,
            "total_tasting_descriptors": 7,
            "total_key_insights": 2,
        },
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "knowledge"
        try:
            split_knowledge_to_files(stub_knowledge, out_dir)
        except KeyError as exc:
            print(f"  FAIL — KeyError in split_knowledge_to_files: {exc}")
            traceback.print_exc()
            return False
        except Exception as exc:
            print(f"  FAIL — Unexpected error: {exc}")
            traceback.print_exc()
            return False

        expected_files = [
            "consensus_claims.md",
            "contested_claims.md",
            "vocabulary.md",
            "tasting_descriptors.md",
            "community_framing.md",
            "insights_by_category.md",
        ]
        missing = []
        for fname in expected_files:
            fpath = out_dir / fname
            if not fpath.exists():
                missing.append(fname)
            else:
                content = fpath.read_text(encoding="utf-8")
                if len(content) < 10:
                    missing.append(f"{fname} (empty)")

        if missing:
            print(f"  FAIL — Missing or empty output files: {missing}")
            return False

        # Spot-check content of key files
        consensus_content = (out_dir / "consensus_claims.md").read_text(encoding="utf-8")
        assert "Light roasts have more acidity" in consensus_content, \
            "consensus_claims.md missing expected claim"
        assert "roast" in consensus_content.lower(), \
            "consensus_claims.md missing category header"

        vocab_content = (out_dir / "vocabulary.md").read_text(encoding="utf-8")
        assert "bloom" in vocab_content, "vocabulary.md missing 'bloom' term"
        assert "channeling" in vocab_content, "vocabulary.md missing 'channeling' term"

        descriptors_content = (out_dir / "tasting_descriptors.md").read_text(encoding="utf-8")
        assert "blueberry" in descriptors_content, "tasting_descriptors.md missing 'blueberry'"

        framing_content = (out_dir / "community_framing.md").read_text(encoding="utf-8")
        assert "src_001" in framing_content, "community_framing.md missing source"

        insights_content = (out_dir / "insights_by_category.md").read_text(encoding="utf-8")
        assert "Water temperature" in insights_content, "insights_by_category.md missing insight"

        print("  PASS — split_knowledge_to_files() consumed schema without errors")
        print(f"  Output files: {', '.join(expected_files)}")
        return True


# ---------------------------------------------------------------------------
# Test 2 — Tool-use parse with quotes/apostrophes + json_repair fallback
# ---------------------------------------------------------------------------

def test_tool_use_parse() -> bool:
    """
    Confirm that block.input (already a dict) survives the compile pipeline even
    when text fields contain quotes, apostrophes, and newlines. Also test the
    json_repair fallback recovers a deliberately malformed text response.
    """
    print("\n=== Test 2: Tool-use parse + fallback ===")
    try:
        from build_skill_knowledge import (
            _extract_tool_input,
            _text_fallback_parse,
            compile_knowledge,
        )
    except ImportError as exc:
        print(f"  FAIL — could not import build_skill_knowledge: {exc}")
        return False

    # Simulate a tool_use block whose input contains quotes and apostrophes
    class FakeBlock:
        def __init__(self, block_type, name=None, input_data=None, text=None):
            self.type = block_type
            self.name = name
            self.input = input_data
            self.text = text

    tricky_input = {
        "summary": "It's a \"great\" coffee — can't go wrong.",
        "consensus_claims": [
            "The grinder's burr set matters more than people \"assume\".",
            "Don't skip the bloom step — it's crucial.",
        ],
        "contested_claims": [
            "Some say \"light roast\" is best for espresso; others won't touch it.",
        ],
        "technical_vocabulary": [
            {"term": "bloom", "usage": "It's the CO2 release: pour ~30g, wait 30s."},
            {"term": "ristretto", "usage": "Half-shot: rich, sweet, \"syrupy\" in texture."},
        ],
        "community_framing": "They value \"consistency\" over \"excitement\" — it's pragmatic.",
        "tasting_descriptors": ["caramel sweetness", "it's fruity", "dark chocolate"],
        "key_insights": [
            "Jackson's rule: grind fresh, don't pre-grind.",
        ],
        "source_perspective": "A hands-on \"pro\" perspective with real-world advice.",
        "products_or_topics_referenced": ["Baratza Encore", "Comandante C40"],
    }

    class FakeResponse:
        def __init__(self, content):
            self.content = content
            self.stop_reason = "tool_use"

    # Test 2a: tool_use block extraction
    response = FakeResponse([
        FakeBlock("tool_use", name="record_source_digest", input_data=tricky_input),
    ])
    result = _extract_tool_input(response)
    if result is None:
        print("  FAIL — _extract_tool_input returned None")
        return False
    if result["summary"] != tricky_input["summary"]:
        print(f"  FAIL — summary mismatch: {result['summary']!r}")
        return False

    # Verify it compiles without errors
    candidate = {
        "source_id": "test_quotes_apostrophes",
        "source": "web",
        "category": "espresso",
        "site_or_channel": "testsite",
        "quality_score": 0.9,
        "text_chars": 500,
        "truncated": False,
    }
    digests = {"test_quotes_apostrophes": result}
    try:
        knowledge = compile_knowledge([candidate], digests, "claude-sonnet-4-6")
    except Exception as exc:
        print(f"  FAIL — compile_knowledge raised {exc}")
        traceback.print_exc()
        return False

    if not knowledge["consensus_claims"]:
        print("  FAIL — no consensus_claims after compilation")
        return False
    if not knowledge["vocabulary"]:
        print("  FAIL — no vocabulary after compilation")
        return False

    print("  PASS 2a — tool_use block with quotes/apostrophes parsed and compiled cleanly")

    # Test 2b: json_repair fallback
    try:
        from json_repair import repair_json  # noqa: F401
        has_json_repair = True
    except ImportError:
        has_json_repair = False

    broken_json = '{"summary": "It\'s broken", "consensus_claims": ["valid claim", "another] }'

    class FakeTextResponse:
        content = [FakeBlock("text", text=broken_json)]
        stop_reason = "end_turn"

    fallback = _text_fallback_parse(FakeTextResponse())
    if has_json_repair and fallback is None:
        print("  FAIL 2b — json_repair fallback returned None on fixable JSON")
        return False
    elif not has_json_repair:
        print("  SKIP 2b — json_repair not installed; text fallback will degrade gracefully")
    else:
        print("  PASS 2b — json_repair fallback recovered broken JSON")

    # Test 2c: text fallback on strict-parseable JSON
    clean_json = json.dumps(tricky_input)
    class FakeCleanTextResponse:
        content = [FakeBlock("text", text=clean_json)]
        stop_reason = "end_turn"
    fallback2 = _text_fallback_parse(FakeCleanTextResponse())
    if fallback2 is None:
        print("  FAIL 2c — text fallback failed on valid JSON")
        return False
    print("  PASS 2c — text fallback parsed clean JSON correctly")

    return True


# ---------------------------------------------------------------------------
# Test 3 — Dry-run against real data (if it exists)
# ---------------------------------------------------------------------------

def test_dry_run() -> bool:
    """Run --dry-run against actual training_data/cleaned/ if present."""
    print("\n=== Test 3: Dry-run on real data ===")

    cleaned_dir = REPO_ROOT / "training_data" / "cleaned"
    if not cleaned_dir.exists():
        print("  SKIP — training_data/cleaned/ does not exist (corpus not collected yet)")
        return True

    import subprocess
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "data_pipeline" / "build_skill_knowledge.py"),
         "--dry-run"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )

    if result.returncode != 0:
        print(f"  FAIL — --dry-run exited with code {result.returncode}")
        print("  STDERR:", result.stderr[-2000:])
        return False

    report_path = REPO_ROOT / "skill_data" / "selection_report.md"
    if not report_path.exists():
        print("  FAIL — selection_report.md not written")
        return False

    print("  PASS — --dry-run completed successfully")
    print("  selection_report.md written")

    # Parse cost estimate from stdout
    stdout = result.stdout
    if "Total cost" in stdout:
        for line in stdout.splitlines():
            if "Total cost" in line or "Selected" in line or "candidates" in line:
                print(f"    {line.strip()}")

    return True


# ---------------------------------------------------------------------------
# Test 4 — Import-time syntax and schema constant check
# ---------------------------------------------------------------------------

def test_import_and_constants() -> bool:
    """Verify the script imports cleanly and key constants are correctly defined."""
    print("\n=== Test 4: Import and constant validation ===")
    try:
        import build_skill_knowledge as bsk
    except ImportError as exc:
        print(f"  FAIL — import error: {exc}")
        return False
    except SyntaxError as exc:
        print(f"  FAIL — syntax error: {exc}")
        return False

    # Check required constants
    checks = [
        ("SELECTION_MIN", bsk.SELECTION_MIN, lambda v: 40 <= v <= 60),
        ("SELECTION_MAX", bsk.SELECTION_MAX, lambda v: 50 <= v <= 70),
        ("TEXT_DIGEST_CAP", bsk.TEXT_DIGEST_CAP, lambda v: v >= 3000),
        ("MAX_PER_WEB_SITE", bsk.MAX_PER_WEB_SITE, lambda v: v == 5),
        ("MAX_PER_YT_CHANNEL", bsk.MAX_PER_YT_CHANNEL, lambda v: v == 4),
        ("MAX_PER_SUBREDDIT", bsk.MAX_PER_SUBREDDIT, lambda v: v == 8),
        ("MIN_PER_CATEGORY", bsk.MIN_PER_CATEGORY, lambda v: v == 2),
        ("CATEGORIES length", len(bsk.CATEGORIES), lambda v: v == 10),
        ("DIGEST_TOOL name", bsk.DIGEST_TOOL["name"], lambda v: v == "record_source_digest"),
    ]

    all_ok = True
    for name, val, check in checks:
        ok = check(val)
        status = "✓" if ok else "✗"
        print(f"  {status} {name} = {val!r}")
        if not ok:
            all_ok = False

    # Check required digest schema fields
    required_fields = {
        "summary", "consensus_claims", "contested_claims", "technical_vocabulary",
        "community_framing", "tasting_descriptors", "key_insights",
        "source_perspective", "products_or_topics_referenced",
    }
    schema_props = set(bsk.DIGEST_TOOL["input_schema"]["properties"].keys())
    missing_schema = required_fields - schema_props
    if missing_schema:
        print(f"  ✗ DIGEST_TOOL missing schema fields: {missing_schema}")
        all_ok = False
    else:
        print(f"  ✓ DIGEST_TOOL has all {len(required_fields)} required schema fields")

    if all_ok:
        print("  PASS — all constants and schema fields validated")
    return all_ok


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main() -> None:
    results = {
        "Test 1 (schema round-trip)": test_schema_round_trip(),
        "Test 2 (tool-use parse)": test_tool_use_parse(),
        "Test 3 (dry-run)": test_dry_run(),
        "Test 4 (import + constants)": test_import_and_constants(),
    }

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    all_passed = True
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {status}  {name}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("All tests passed.")
        sys.exit(0)
    else:
        print("Some tests FAILED. See output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
