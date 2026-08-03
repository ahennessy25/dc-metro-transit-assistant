"""Tool-routing verification harness for the DC Transit Assistant.

Live mode runs the shared eval set through agent.core.ask() and checks whether
Claude called the expected tools in order. Dry-run mode does not call Claude;
it feeds each case's expected tools back through the same report pipeline so the
team can validate the harness, log format, and case coverage without an
ANTHROPIC_API_KEY.

Run live:
    python -m agent.verification_harness

Run without an Anthropic key:
    python -m agent.verification_harness --dry-run

List cases only:
    python -m agent.verification_harness --list
"""

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from agent.core import MissingAnthropicApiKeyError, ask
from agent.eval_cases import EVAL_CASES
from config import ANTHROPIC_API_KEY

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

RESULTS_LOG_PATH = Path(__file__).parent / "verification_results.log"

_CLARIFYING_QUESTION_PATTERNS = [
    r"\?",
    r"\bcould you clarify\b",
    r"\bcan you clarify\b",
    r"\bwhich station\b",
    r"\bwhich line\b",
    r"\bdid you mean\b",
    r"\bcan you (specify|confirm)\b",
]


class HarnessConfigurationError(RuntimeError):
    """Raised when the eval case table itself is malformed."""


def _looks_like_clarifying_question(answer: str) -> bool:
    lowered = answer.lower()
    return any(re.search(pattern, lowered) for pattern in _CLARIFYING_QUESTION_PATTERNS)


def _is_ordered_subsequence(expected: list, actual: list) -> bool:
    """True if `expected` appears in `actual`, in order.

    Extra items in `actual` do not break the match; they are logged for human
    review because some multi-part questions can reasonably use bonus tools.
    """
    it = iter(actual)
    return all(item in it for item in expected)


def _validate_cases(cases: list[dict]) -> None:
    required_keys = {"question", "expected_tools", "expected_args", "notes", "category"}
    questions = set()
    for index, case in enumerate(cases, start=1):
        missing = required_keys - set(case)
        if missing:
            raise HarnessConfigurationError(f"Case {index} is missing required keys: {sorted(missing)}")
        if not isinstance(case["question"], str) or not case["question"].strip():
            raise HarnessConfigurationError(f"Case {index} has an empty question")
        if case["question"] in questions:
            raise HarnessConfigurationError(f"Duplicate question in eval set: {case['question']}")
        questions.add(case["question"])
        if not isinstance(case["expected_tools"], list):
            raise HarnessConfigurationError(f"Case {index} expected_tools must be a list")
        if not isinstance(case["expected_args"], dict):
            raise HarnessConfigurationError(f"Case {index} expected_args must be a dict")


def _dry_run_answer(case: dict) -> dict:
    expected_tools = case["expected_tools"]
    tool_calls = [
        {
            "name": tool_name,
            "args": case.get("expected_args", {}).get(tool_name, {}),
        }
        for tool_name in expected_tools
    ]
    if expected_tools:
        answer = "DRY RUN: simulated expected tool routing; no Claude/API call was made."
    else:
        answer = "DRY RUN: simulated no-tool response. Which station or line did you mean?"
    return {"answer": answer, "tool_calls": tool_calls}


def _run_case(case: dict, ask_func=ask) -> dict:
    result = ask_func(case["question"])
    actual_tool_names = [call["name"] for call in result["tool_calls"]]
    expected_tools = case["expected_tools"]

    is_no_tool_case = expected_tools == []
    if is_no_tool_case:
        tools_pass = actual_tool_names == []
    else:
        tools_pass = _is_ordered_subsequence(expected_tools, actual_tool_names)

    extra_tools = [name for name in actual_tool_names if name not in expected_tools]

    heuristic_flag = None
    if is_no_tool_case:
        heuristic_flag = (
            "looks like a clarifying question"
            if _looks_like_clarifying_question(result["answer"])
            else "does NOT look like a clarifying question - check for silent guessing"
        )

    return {
        "case": case,
        "result": result,
        "actual_tool_names": actual_tool_names,
        "tools_pass": tools_pass,
        "extra_tools": extra_tools,
        "needs_human_read": is_no_tool_case,
        "heuristic_flag": heuristic_flag,
    }


def _format_case_log(index: int, total: int, run: dict) -> str:
    case = run["case"]
    result = run["result"]

    if run["needs_human_read"]:
        status = "NEEDS HUMAN READ"
    elif run["tools_pass"]:
        status = "PASS"
    else:
        status = "FAIL"

    lines = [
        f"[{index}/{total}] {status}  ({case['category']})",
        f"  Q: {case['question']}",
        f"  expected tools: {case['expected_tools']}",
        f"  actual tools:   {run['actual_tool_names']}",
    ]

    if run["extra_tools"]:
        lines.append(f"  extra tools called (not necessarily a problem): {run['extra_tools']}")

    for call in result["tool_calls"]:
        expected_args = case.get("expected_args", {}).get(call["name"])
        lines.append(f"  tool call: {call['name']}({call['args']})")
        if expected_args is not None:
            lines.append(f"    expected args (for reference, not asserted): {expected_args}")

    if run["heuristic_flag"]:
        lines.append(f"  heuristic: {run['heuristic_flag']}")

    if case.get("notes"):
        lines.append(f"  notes: {case['notes']}")

    lines.append(f"  answer: {result['answer']}")
    lines.append("-" * 80)
    return "\n".join(lines)


def _summary_lines(runs: list[dict]) -> list[str]:
    checked_runs = [r for r in runs if not r["needs_human_read"]]
    human_read_runs = [r for r in runs if r["needs_human_read"]]

    passed = sum(1 for r in checked_runs if r["tools_pass"])
    failed_runs = [r for r in checked_runs if not r["tools_pass"]]
    clarifying_count = sum(
        1 for r in human_read_runs if r["heuristic_flag"] == "looks like a clarifying question"
    )

    lines = [
        "",
        "=== SUMMARY ===",
        f"Tool-routing checks: {passed}/{len(checked_runs)} passed",
    ]

    if failed_runs:
        lines.append("Failures:")
        for r in failed_runs:
            lines.append(
                f"  - \"{r['case']['question']}\" "
                f"expected {r['case']['expected_tools']}, got {r['actual_tool_names']}"
            )

    lines.append(
        f"Ambiguity/out-of-scope cases: {len(human_read_runs)} total, all need human read "
        f"({clarifying_count} looked like a clarifying question by the heuristic, "
        f"{len(human_read_runs) - clarifying_count} did not)"
    )
    lines.append("")
    return lines


def run_verification(*, dry_run: bool = False, log_path: Path = RESULTS_LOG_PATH) -> list[dict]:
    _validate_cases(EVAL_CASES)
    if not dry_run and not ANTHROPIC_API_KEY:
        raise MissingAnthropicApiKeyError(
            "ANTHROPIC_API_KEY is not set. Add it to .env for live Claude chat calls. "
            "Non-LLM setup tasks, WMATA/weather scripts, RAG indexing, and unit tests can "
            "still run without it."
        )

    timestamp = datetime.now(timezone.utc).isoformat()
    mode = "DRY RUN" if dry_run else "LIVE"
    header = f"=== Verification run: {timestamp} ({mode}) ==="

    runs = []

    with open(log_path, "a", encoding="utf-8") as log_file:
        def emit(text):
            print(text)
            log_file.write(text + "\n")
            log_file.flush()

        emit(header)
        for i, case in enumerate(EVAL_CASES, start=1):
            ask_func = (lambda _question, case=case: _dry_run_answer(case)) if dry_run else ask
            run = _run_case(case, ask_func=ask_func)
            runs.append(run)
            emit(_format_case_log(i, len(EVAL_CASES), run))

        emit("\n".join(_summary_lines(runs)))

    print(f"\nFull results appended to {log_path}")
    return runs


def list_cases() -> None:
    _validate_cases(EVAL_CASES)
    for i, case in enumerate(EVAL_CASES, start=1):
        expected = ", ".join(case["expected_tools"]) or "no tools"
        print(f"{i:02d}. [{case['category']}] {case['question']} -> {expected}")


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run or inspect the DC Transit Assistant eval set.")
    parser.add_argument("--dry-run", action="store_true", help="Generate a report without calling Claude.")
    parser.add_argument("--list", action="store_true", help="List eval cases without running them.")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    if args.list:
        list_cases()
        return 0
    try:
        run_verification(dry_run=args.dry_run)
    except MissingAnthropicApiKeyError as e:
        print(f"[Error] {e}")
        print("Run with --dry-run to validate the harness without an Anthropic key.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
