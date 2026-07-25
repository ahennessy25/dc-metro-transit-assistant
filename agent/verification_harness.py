"""Week 2 tool-routing verification harness.

Runs a fixed table of test questions through agent.core.ask() and checks
whether the tools actually called match what we expect, in order. Argument
values are logged for human comparison but never asserted on automatically
(exact argument matching is brittle — a station resolved as "Metro Center"
vs "METRO CENTER" isn't a routing bug).

Two kinds of check:
- Cases with a non-empty `expected_tools`: PASS if those tools appear, in
  order, anywhere in the actual tool-call sequence (extra tools beyond the
  expected ones are logged but not treated as a failure — see NOTE below).
- Cases with `expected_tools: []` (ambiguity/out-of-scope): PASS only means
  "no tool was called." It does NOT confirm the agent asked a clarifying
  question instead of silently guessing — these are always marked "needs
  human read" regardless, with a soft heuristic flag (does the answer look
  like a question?) to help a reviewer scan faster, not to replace reading
  the actual answer text in the log.

NOTE on "extra tools": a question like "should I bike or take the train"
might reasonably pull in a bonus tool (e.g. search_station_info for bike
policy) beyond what's minimally expected. That's treated as a fine, even
good, answer — not a routing failure — as long as the expected tools are
still present in the right order. Extra tools are still logged so a
reviewer can judge for themselves.

Run with: python -m agent.verification_harness
(NOT `python agent/verification_harness.py` directly — running it as a
bare script instead of a module breaks the `agent.core` import, since the
project root wouldn't be on sys.path. Same reason noted in
agent/manual_test.py.)
"""

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from agent.core import ask

# Windows consoles often default to cp1252, which can't print characters
# Claude's answers commonly include (em dashes, degree signs, arrows, emoji).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

RESULTS_LOG_PATH = Path(__file__).parent / "verification_results.log"

# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------
# Each case: question, expected_tools (ordered; [] means "no tool call
# expected"), expected_args (optional, per-tool, logged not asserted),
# notes (what "correct" looks like / known caveats), category (for grouping
# in the log and summary).

TEST_CASES = [
    # --- Week 1: single-tool cases (raw deliverable examples) ---
    {
        "question": "What's the next 3 Red Line arrivals at Metro Center?",
        "expected_tools": ["get_real_time_arrivals"],
        "expected_args": {"get_real_time_arrivals": {"station": "Metro Center"}},
        "notes": "Straightforward single-tool live-arrivals lookup.",
        "category": "week1",
    },
    {
        "question": "Are there active alerts on the Blue Line?",
        "expected_tools": ["get_service_alerts"],
        "expected_args": {"get_service_alerts": {"line": "Blue"}},
        "notes": "Straightforward single-tool alerts lookup.",
        "category": "week1",
    },
    {
        "question": "What's the weather right now?",
        "expected_tools": ["get_weather"],
        "expected_args": {"get_weather": {"when": "now"}},
        "notes": "Straightforward single-tool current-conditions lookup.",
        "category": "week1",
    },
    # --- Week 2: multi-tool / reasoning cases ---
    {
        "question": "Is the Red Line running normally right now?",
        "expected_tools": ["get_service_alerts"],
        "expected_args": {"get_service_alerts": {"line": "Red"}},
        "notes": (
            "NOT ambiguous with get_real_time_arrivals: that tool requires a "
            "specific station and can't answer a line-wide question. "
            "get_service_alerts is the tool that carries segment-specific "
            "disruption info (e.g. construction on part of the line while "
            "the rest runs fine). A get_real_time_arrivals call here is a "
            "real routing bug, not a judgment call."
        ),
        "category": "week2",
    },
    {
        "question": "What's the weather looking like for my commute tomorrow morning?",
        "expected_tools": ["get_weather"],
        "expected_args": {"get_weather": {"when": "tomorrow"}},
        "notes": (
            "CORRECTED from the original spec, which expected get_weather + "
            "get_real_time_arrivals. get_real_time_arrivals only returns "
            "LIVE current predictions, not tomorrow's, and no station is "
            "named in the question — there's nothing for it to be called "
            "with. This should be get_weather only."
        ),
        "category": "week2",
    },
    {
        "question": "How do I get from Dupont Circle to Union Station, and are there any delays?",
        "expected_tools": ["get_service_alerts"],
        "expected_args": {"get_service_alerts": {}},
        "notes": (
            "CORRECTED from the original spec, which expected "
            "get_scheduled_times + get_service_alerts. get_scheduled_times "
            "(route, stop) needs an already-known route — none of the 5 "
            "tools do station-to-station route-finding. Claude should "
            "answer 'which line connects these stations' from general "
            "knowledge and only call get_service_alerts for the delays part."
        ),
        "category": "week2",
    },
    # --- Edge case: segment naming should still route to alerts, not arrivals ---
    {
        "question": "Are trains running normally between Shady Grove and Friendship Heights?",
        "expected_tools": ["get_service_alerts"],
        "expected_args": {"get_service_alerts": {"line": "Red"}},
        "notes": (
            "Naming two stations as a segment is still asking about "
            "disruption status, not a specific train's arrival time. A "
            "get_real_time_arrivals call here is a real routing bug worth "
            "flagging, not a judgment call — same reasoning as the "
            "'is the Red Line running normally' case above, from a "
            "different angle."
        ),
        "category": "edge_case",
    },
    # --- Additional explicit multi-tool case ---
    {
        "question": "Should I bike or take the train tomorrow morning?",
        "expected_tools": ["get_weather", "get_service_alerts"],
        "expected_args": {"get_weather": {"when": "tomorrow"}, "get_service_alerts": {}},
        "notes": (
            "The plan doc's own example of multi-tool reasoning. A bonus "
            "third call to search_station_info (bike policy FAQ) has been "
            "observed in manual testing and is a fine, even better, "
            "answer — not a routing failure — as long as get_weather and "
            "get_service_alerts both still appear in order."
        ),
        "category": "multi_tool_extra",
    },
    # --- Rephrasings: same expected routing, different wording ---
    {
        "question": "Is the Blue Line experiencing any disruptions right now?",
        "expected_tools": ["get_service_alerts"],
        "expected_args": {"get_service_alerts": {"line": "Blue"}},
        "notes": "Rephrasing of the Week 1 Blue Line alerts case.",
        "category": "rephrase",
    },
    {
        "question": "How's the weather looking outside at the moment?",
        "expected_tools": ["get_weather"],
        "expected_args": {"get_weather": {"when": "now"}},
        "notes": "Rephrasing of the Week 1 current-weather case.",
        "category": "rephrase",
    },
    {
        "question": "When are the next few Red Line trains coming into Metro Center?",
        "expected_tools": ["get_real_time_arrivals"],
        "expected_args": {"get_real_time_arrivals": {"station": "Metro Center"}},
        "notes": "Rephrasing of the Week 1 Metro Center arrivals case.",
        "category": "rephrase",
    },
    {
        "question": "Any issues on the Red Line at the moment?",
        "expected_tools": ["get_service_alerts"],
        "expected_args": {"get_service_alerts": {"line": "Red"}},
        "notes": "Rephrasing of the 'is the Red Line running normally' case.",
        "category": "rephrase",
    },
    {
        "question": "Would it make more sense to bike or ride the train in tomorrow?",
        "expected_tools": ["get_weather", "get_service_alerts"],
        "expected_args": {"get_weather": {"when": "tomorrow"}, "get_service_alerts": {}},
        "notes": "Rephrasing of the bike-or-train multi-tool case.",
        "category": "rephrase",
    },
    # --- Ambiguity cases ---
    # Two of these are genuine multi-way ambiguity (no confident best guess
    # — a clarifying question with no tool call is correct). The other three
    # are confident-guess typos/short-forms, where the system prompt we
    # wrote actually calls for a STATED ASSUMPTION *and* a tool call, not
    # silence. expected_tools: [] is used for all 5 per instruction, but
    # the notes flag which is which — don't read a "FAIL" on tools for the
    # typo cases as a bug; read the actual answer text in the log instead.
    {
        "question": "When's the next train at Farragut?",
        "expected_tools": [],
        "expected_args": {},
        "notes": (
            "GENUINE ambiguity: Farragut North and Farragut West are two "
            "distinct, non-interchangeable real stations. A clarifying "
            "question with no tool call is the correct behavior here."
        ),
        "category": "ambiguity",
    },
    {
        "question": "Is the express line delayed?",
        "expected_tools": [],
        "expected_args": {},
        "notes": (
            "GENUINE ambiguity: WMATA has no 'express line' — riders "
            "sometimes use this loosely for Silver/Orange, but there's no "
            "single best guess. A clarifying question is correct."
        ),
        "category": "ambiguity",
    },
    {
        "question": "When's the next train at Dupont?",
        "expected_tools": [],
        "expected_args": {},
        "notes": (
            "CONFIDENT-GUESS case, not genuine ambiguity: only one WMATA "
            "station starts with 'Dupont'. Per the system prompt, correct "
            "behavior is to state the assumption ('Assuming you mean "
            "Dupont Circle...') AND still call get_real_time_arrivals. "
            "expected_tools: [] is very likely to show as a tool-routing "
            "FAIL here even when the agent behaves exactly as designed — "
            "check the human-read log, not the pass/fail count."
        ),
        "category": "ambiguity",
    },
    {
        "question": "When's the next Sliver line train at Rosslyn?",
        "expected_tools": [],
        "expected_args": {},
        "notes": (
            "CONFIDENT-GUESS case (obvious typo: 'Sliver' -> 'Silver'), not "
            "genuine ambiguity. Correct behavior per the system prompt is a "
            "stated assumption plus a get_real_time_arrivals call. Same "
            "caveat as the Dupont case above — likely FAIL by design."
        ),
        "category": "ambiguity",
    },
    {
        "question": "What time's the last train at King St?",
        "expected_tools": [],
        "expected_args": {},
        "notes": (
            "CONFIDENT-GUESS case ('King St' -> 'King St-Old Town'), not "
            "genuine ambiguity. Correct behavior per the system prompt is a "
            "stated assumption plus a tool call. Same caveat as the Dupont "
            "and Sliver cases above — likely FAIL by design."
        ),
        "category": "ambiguity",
    },
    # --- Out-of-scope cases (Metrobus — this project is Metrorail-only) ---
    {
        "question": "What time does the 70 bus come?",
        "expected_tools": [],
        "expected_args": {},
        "notes": "Metrobus route schedule — out of scope, no tool covers this.",
        "category": "out_of_scope",
    },
    {
        "question": "Is the H8 Metrobus running on time?",
        "expected_tools": [],
        "expected_args": {},
        "notes": "Metrobus live status — out of scope, no tool covers this.",
        "category": "out_of_scope",
    },
    {
        "question": "Where's the closest Metrobus stop to Dupont Circle?",
        "expected_tools": [],
        "expected_args": {},
        "notes": "Metrobus stop location — out of scope, no tool covers this.",
        "category": "out_of_scope",
    },
]

# ---------------------------------------------------------------------------
# Heuristics
# ---------------------------------------------------------------------------

_CLARIFYING_QUESTION_PATTERNS = [
    r"\?",
    r"\bcould you clarify\b",
    r"\bcan you clarify\b",
    r"\bwhich station\b",
    r"\bwhich line\b",
    r"\bdid you mean\b",
    r"\bcan you (specify|confirm)\b",
]


def _looks_like_clarifying_question(answer: str) -> bool:
    lowered = answer.lower()
    return any(re.search(pattern, lowered) for pattern in _CLARIFYING_QUESTION_PATTERNS)


def _is_ordered_subsequence(expected: list, actual: list) -> bool:
    """True if `expected` appears in `actual`, in order. Extra items in
    `actual` (beyond what's expected) don't break the match.
    """
    it = iter(actual)
    return all(item in it for item in expected)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def _run_case(case: dict) -> dict:
    result = ask(case["question"])
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
            else "does NOT look like a clarifying question — check for silent guessing"
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


def run_verification():
    timestamp = datetime.now(timezone.utc).isoformat()
    header = f"=== Verification run: {timestamp} ==="

    # Written incrementally (one case at a time, flushed immediately)
    # rather than batched into memory and written once at the end — a
    # crash partway through (a bad API response, an encoding error on
    # print, etc.) would otherwise lose every already-completed case, and
    # those already cost real API calls to produce.
    log_file = open(RESULTS_LOG_PATH, "a", encoding="utf-8")

    def emit(text):
        print(text)
        log_file.write(text + "\n")
        log_file.flush()

    try:
        emit(header)

        runs = []
        for i, case in enumerate(TEST_CASES, start=1):
            run = _run_case(case)
            runs.append(run)
            emit(_format_case_log(i, len(TEST_CASES), run))

        checked_runs = [r for r in runs if not r["needs_human_read"]]
        human_read_runs = [r for r in runs if r["needs_human_read"]]

        passed = sum(1 for r in checked_runs if r["tools_pass"])
        failed_runs = [r for r in checked_runs if not r["tools_pass"]]

        clarifying_count = sum(
            1 for r in human_read_runs if r["heuristic_flag"] == "looks like a clarifying question"
        )

        summary_lines = [
            "",
            "=== SUMMARY ===",
            f"Tool-routing checks: {passed}/{len(checked_runs)} passed",
        ]

        if failed_runs:
            summary_lines.append("Failures:")
            for r in failed_runs:
                summary_lines.append(
                    f"  - \"{r['case']['question']}\" "
                    f"expected {r['case']['expected_tools']}, got {r['actual_tool_names']}"
                )

        summary_lines.append(
            f"Ambiguity/out-of-scope cases: {len(human_read_runs)} total, all need human read "
            f"({clarifying_count} looked like a clarifying question by the heuristic, "
            f"{len(human_read_runs) - clarifying_count} did not)"
        )
        summary_lines.append("")

        emit("\n".join(summary_lines))
    finally:
        log_file.close()

    print(f"\nFull results appended to {RESULTS_LOG_PATH}")


if __name__ == "__main__":
    run_verification()
