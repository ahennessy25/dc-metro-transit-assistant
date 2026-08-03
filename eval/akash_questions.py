"""
This is a different kind of check than agent/verification_harness.py: that
harness asserts on which *tools* got called (routing correctness). These
questions are for judging the *answer itself* — is it accurate, complete,
and honest about what it doesn't know — since a case can call the right
tool and still give a bad answer (e.g. hallucinating a detail the tool
result didn't actually contain).

This file holds 10 of the team's target 20-30 questions, split across the
four categories called for: schedule lookups, live status, weather, and
multi-part questions. Each entry has no single "correct string" to match
against (transit conditions change), so `good_answer_should` is a checklist
for a human reviewer (or a future LLM-judge) rather than an automated
assertion — same spirit as verification_harness.py's ambiguity cases, which
are marked "needs human read" instead of pass/fail.

Run informally with:
    from agent.core import ask
    from eval.akash_questions import QUESTIONS
    for q in QUESTIONS:
        print(q["question"])
        print(ask(q["question"])["answer"])
"""

QUESTIONS = [
    # --- Schedule lookups (static GTFS) ---
    {
        "question": "What time does the first Red Line train leave Shady Grove on a weekday morning?",
        "category": "schedule_lookup",
        "good_answer_should": [
            "give a specific first-departure time, not a vague 'early morning'",
            "call out that it's a weekday schedule specifically, since weekend service differs",
        ],
        "notes": "Straightforward first-train lookup; a good baseline case.",
    },
    {
        "question": "What's the last train from Metro Center to Vienna on a Saturday night?",
        "category": "schedule_lookup",
        "good_answer_should": [
            "give a specific last-departure time for Saturday, not weekday service",
            "not silently substitute weekday hours for weekend hours",
        ],
        "notes": (
            "Deliberately mirrors the King St 'last train' bug noted in "
            "DECISIONS.md (get_scheduled_times previously truncated away "
            "late-day times) — good regression case for that fix."
        ),
    },
    {
        "question": "How frequently do Blue Line trains run during evening rush hour?",
        "category": "schedule_lookup",
        "good_answer_should": [
            "answer with a headway (e.g. 'about every N minutes'), not just a single time",
            "specify it's for evening rush hour, not an all-day average",
        ],
        "notes": "Tests whether the assistant can reason about frequency, not just single departure times.",
    },
    # --- Live status (GTFS-Realtime: arrivals + alerts) ---
    {
        "question": "Are there any delays on the Orange Line right now?",
        "category": "live_status",
        "good_answer_should": [
            "reflect current alert data, not general knowledge about the Orange Line",
            "clearly say 'no known delays' if the alerts feed is empty, rather than hedging vaguely",
        ],
        "notes": "Basic live-alerts case; also useful as an accuracy check against a manually-checked WMATA status page at eval time.",
    },
    {
        "question": "What are the next three trains arriving at Gallery Place?",
        "category": "live_status",
        "good_answer_should": [
            "list three distinct arrival predictions with times/lines, not a static schedule",
            "note if fewer than three predictions are actually available rather than inventing extras",
        ],
        "notes": "Gallery Place serves both Red and Green/Yellow lines — checks the answer doesn't drop one line's predictions silently.",
    },
    {
        "question": "Is the Yellow Line bridge over the Potomac currently open?",
        "category": "live_status",
        "good_answer_should": [
            "answer from live alert data (the Yellow Line bridge has a real history of closures/single-tracking)",
            "not confidently assert normal service if there's no alert data to confirm it either way",
        ],
        "notes": "Tests honesty under uncertainty — a case where 'no alert found' should be phrased carefully, not as a confident guarantee.",
    },
    # --- Weather ---
    {
        "question": "Will it rain during my commute this evening?",
        "category": "weather",
        "good_answer_should": [
            "use the forecast tool for 'this evening', not current conditions",
            "give a clear yes/no/maybe with the reasoning (e.g. chance of precipitation)",
        ],
        "notes": "Tests forecast vs. current-conditions tool selection from an implicit time reference.",
    },
    {
        "question": "What's the temperature going to be tomorrow morning at Union Station?",
        "category": "weather",
        "good_answer_should": [
            "give the DC-area forecast (NWS doesn't provide per-station granularity)",
            "not fabricate a station-specific microclimate reading it doesn't actually have",
        ],
        "notes": (
            "Deliberately probes for a known failure mode: the weather tool "
            "is DC-area-wide, not per-station, so a good answer generalizes "
            "honestly instead of pretending to know conditions specifically "
            "at Union Station."
        ),
    },
    # --- Multi-part ---
    {
        "question": "Is the Silver Line running on time, and should I bring an umbrella for my walk to the station?",
        "category": "multi_part",
        "good_answer_should": [
            "call both the alerts tool and the weather tool and answer both halves",
            "not answer only the transit half and drop the weather half (or vice versa)",
        ],
        "notes": "Two independent sub-questions in one message — checks neither gets dropped.",
    },
    {
        "question": "I'm heading from Bethesda to Capitol South — what time's the next train, and are there any elevator outages I should know about?",
        "category": "multi_part",
        "good_answer_should": [
            "answer the live-arrivals half for Bethesda specifically",
            "answer the accessibility/elevator-outage half (alerts and/or station info retrieval), or "
            "clearly say it doesn't have that information if no tool covers it, rather than guessing",
        ],
        "notes": (
            "Elevator/escalator outage info may not be fully covered by any "
            "single tool — a good answer is honest about that gap instead "
            "of inventing an outage status. Worth flagging for human review "
            "either way."
        ),
    },
]
