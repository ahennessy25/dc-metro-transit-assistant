"""Sanity checks on eval/akash_questions.py — structural only. The actual
question quality is judged by a human (or a future LLM-judge) against
`good_answer_should`, not by this test; this just guards against typos
breaking the shape teammates will merge their own question sets into.
"""

from eval.akash_questions import QUESTIONS

EXPECTED_CATEGORIES = {"schedule_lookup", "live_status", "weather", "multi_part"}


def test_has_ten_questions():
    assert len(QUESTIONS) == 10


def test_every_question_has_required_fields():
    for q in QUESTIONS:
        assert q["question"].strip()
        assert q["category"] in EXPECTED_CATEGORIES
        assert isinstance(q["good_answer_should"], list) and q["good_answer_should"]
        assert q["notes"].strip()


def test_covers_all_four_required_categories():
    categories = {q["category"] for q in QUESTIONS}
    assert categories == EXPECTED_CATEGORIES


def test_questions_are_unique():
    questions = [q["question"] for q in QUESTIONS]
    assert len(questions) == len(set(questions))
