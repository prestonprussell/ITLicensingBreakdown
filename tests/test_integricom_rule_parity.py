"""Parity lock for the rule-driven Integricom allocation refactor.

The allocation engine was refactored from a hardcoded if/elif chain to read
DB-backed rules. These tests prove the refactor did NOT change any numbers:
1. The rule-driven engine reproduces a golden baseline captured from the
   pre-refactor code (everything except the additive `rule_prompts` field).
2. Running with rules loaded from a freshly-seeded SQLite DB produces output
   identical to running with the in-code defaults (the seed round-trips).
"""
import json
from pathlib import Path

from app import integricom_directory
from tests._golden_fixture import canonical_output

GOLDEN_PATH = Path(__file__).parent / "golden_baseline.json"


def _strip_rule_prompts(payload: dict) -> dict:
    # rule_prompts is a NEW additive field (learn-on-unknown); the golden
    # baseline predates it, so it is compared separately.
    return {k: v for k, v in payload.items() if k != "rule_prompts"}


def test_refactor_matches_pre_refactor_golden() -> None:
    golden = json.loads(GOLDEN_PATH.read_text())
    current = json.loads(canonical_output())  # rules=None -> _DEFAULT_RULES

    assert _strip_rule_prompts(current) == _strip_rule_prompts(golden)


def test_unknown_line_now_emits_rule_prompt() -> None:
    current = json.loads(canonical_output())
    # The fixture includes one genuinely unconfigured line.
    assert current["rule_prompts"] == [{"canonical_name": "Totally Unknown Charge XYZ"}]


def test_db_seeded_rules_match_default_rules(tmp_path: Path) -> None:
    integricom_directory.INTEGRICOM_DIRECTORY_DB = tmp_path / "integricom_users.sqlite3"
    integricom_directory.init_integricom_directory()
    db_rules = integricom_directory.load_allocation_rules()

    default_out = json.loads(canonical_output())
    db_out = json.loads(canonical_output(rules=db_rules))

    assert default_out == db_out
