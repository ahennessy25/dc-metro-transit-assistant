"""Runs ask() against a handful of representative questions and prints each
question + answer, for manual eyeballing of answer quality — not a pytest
file, nothing here is asserted automatically.
"""

import sys

from agent.core import ask

# Windows consoles often default to cp1252, which can't print characters
# Claude's answers commonly include (em dashes, degree signs, emoji).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

QUESTIONS = [
    "Is the Red Line running normally right now?",
    "What's the weather looking like for my commute tomorrow morning?",
    "How do I get from Dupont Circle to Union Station, and are there any delays?",
    "Is there an elevator at Dupont Circle?",
    "What's the accessibility situation like at Rosslyn station?",
    "Is Gallery Place-Chinatown wheelchair accessible?",
]

if __name__ == "__main__":
    for i, question in enumerate(QUESTIONS, start=1):
        print(f"[{i}/{len(QUESTIONS)}] Q: {question}")
        result = ask(question)
        if result["tool_calls"]:
            for call in result["tool_calls"]:
                print(f"    tool: {call['name']}({call['args']})")
        print(f"A: {result['answer']}")
        print("-" * 80)
