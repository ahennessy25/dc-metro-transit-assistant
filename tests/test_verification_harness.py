"""Tests for the verification harness mechanics that do not call Claude."""

from agent import verification_harness as harness
from agent.eval_cases import EVAL_CASES


def test_eval_set_matches_task_specific_checklist_categories():
    assert len(EVAL_CASES) == 18

    categories = {case["category"] for case in EVAL_CASES}
    assert categories == {
        "lec_variation",
        "aditi_ambiguity",
        "lec_out_of_scope_metrobus",
    }

    assert sum(case["category"] == "lec_variation" for case in EVAL_CASES) == 10
    assert sum(case["category"] == "aditi_ambiguity" for case in EVAL_CASES) == 5
    assert sum(case["category"] == "lec_out_of_scope_metrobus" for case in EVAL_CASES) == 3

    out_of_scope_questions = [
        case["question"] for case in EVAL_CASES if case["category"] == "lec_out_of_scope_metrobus"
    ]
    assert out_of_scope_questions == [
        "What time does the D40 bus come?",
        "Is the D74 Rhode Island Av-Foggy BottomGo running on time?",
        "Where's the closest Metrobus stop to Dupont Circle?",
    ]

    harness._validate_cases(EVAL_CASES)


def test_dry_run_verification_uses_expected_tools_without_claude(tmp_path):
    log_path = tmp_path / "verification.log"

    runs = harness.run_verification(dry_run=True, log_path=log_path)

    assert len(runs) == len(EVAL_CASES)
    assert log_path.exists()
    assert "DRY RUN" in log_path.read_text(encoding="utf-8")

    checked_runs = [run for run in runs if not run["needs_human_read"]]
    assert checked_runs
    assert all(run["tools_pass"] for run in checked_runs)


def test_live_main_without_key_explains_dry_run_option(monkeypatch, capsys):
    def fake_run_verification(*, dry_run=False):
        raise harness.MissingAnthropicApiKeyError("missing key")

    monkeypatch.setattr(harness, "run_verification", fake_run_verification)

    exit_code = harness.main([])

    assert exit_code == 2
    output = capsys.readouterr().out
    assert "missing key" in output
    assert "--dry-run" in output
