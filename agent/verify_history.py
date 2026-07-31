"""Runs ask() through a couple of multi-turn conversations to manually verify
that conversation_history actually carries context between turns, rather than
each follow-up being answered in isolation. Not a pytest file — nothing here
is asserted automatically, just printed for eyeballing.

History is built the same way agent/app.py builds it from Gradio: plain
{"role": "user"/"assistant", "content": <text>} pairs using each turn's final
answer, not the raw tool_use/tool_result blocks from inside ask()'s loop.
"""

import sys

from agent.core import ask

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

# Each conversation is a list of follow-up questions where later turns
# deliberately omit context (station/line names) that only makes sense if
# the prior turn's context carried over.
CONVERSATIONS = [
    [
        "Is the Red Line running normally?",
        "What about the Blue Line?",
    ],
    [
        "Is there an elevator at Dupont Circle?",
        "What about at Rosslyn?",
    ],
]

if __name__ == "__main__":
    for i, turns in enumerate(CONVERSATIONS, start=1):
        print(f"===== Conversation {i}/{len(CONVERSATIONS)} =====")
        history = []
        for j, question in enumerate(turns, start=1):
            print(f"[{j}/{len(turns)}] Q: {question}")
            result = ask(question, conversation_history=history)
            if result["tool_calls"]:
                for call in result["tool_calls"]:
                    print(f"    tool: {call['name']}({call['args']})")
            print(f"A: {result['answer']}")

            history.append({"role": "user", "content": question})
            history.append({"role": "assistant", "content": result["answer"]})
        print("-" * 80)
