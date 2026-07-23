"""Agent loop: sends a question to Claude with the tools from agent/tools.py,
executing tool calls Claude asks for — including multiple tools in one
response (e.g. weather + schedule) and multiple sequential rounds (a tool
result leading Claude to ask for another tool) — until Claude returns a
final text-only answer or MAX_TOOL_ITERATIONS is hit.
"""

import json

import anthropic

from agent.tools import TOOL_FUNCTIONS, TOOL_SCHEMAS
from config import ANTHROPIC_API_KEY

MODEL = "claude-sonnet-5"
MAX_TOKENS = 1024
MAX_TOOL_ITERATIONS = 5

SYSTEM_PROMPT = (
    "You are a helpful assistant for DC-area Metrorail transit questions. "
    "Use the available tools to answer questions about schedules, live "
    "arrivals, service alerts, weather, and station accessibility/FAQ info. "
    "Don't answer questions about current transit or weather conditions "
    "from general knowledge — always use a tool for those.\n\n"
    "If a station name or line reference is ambiguous, unclear, or looks "
    "misspelled, don't silently guess and answer as if you were certain. "
    "Instead:\n"
    "- If you can make a confident, reasonable guess (an obvious typo or a "
    "well-known short form, e.g. \"Gallery Pl\" or \"Metro Ctr\"), state "
    "your assumption explicitly before answering — e.g. \"Assuming you "
    "mean Metro Center...\" — so the user can correct you if it's wrong.\n"
    "- If there's no clear best guess (the question could plausibly mean "
    "several different stations or lines), ask a brief clarifying "
    "question instead of picking one.\n"
    "Never pick a station or line silently without flagging it one way or "
    "the other."
)

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def ask(user_question: str) -> str:
    """Answers a question, executing tool calls (possibly several, possibly
    over several rounds) until Claude gives a final text-only answer.
    """
    messages = [{"role": "user", "content": user_question}]

    for _ in range(MAX_TOOL_ITERATIONS):
        response = _client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        tool_use_blocks = [block for block in response.content if block.type == "tool_use"]
        if not tool_use_blocks:
            return _extract_text(response)

        messages.append({"role": "assistant", "content": response.content})
        messages.append(
            {
                "role": "user",
                "content": [_run_tool(block) for block in tool_use_blocks],
            }
        )

    # Hit MAX_TOOL_ITERATIONS with Claude still wanting to call tools.
    # Make one last call with no `tools` param — Claude can't ask for
    # another tool, so it's forced to synthesize a text answer from
    # whatever's already been gathered, instead of looping forever or the
    # caller getting nothing back.
    final_response = _client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=messages,
    )
    return _extract_text(final_response)


def _run_tool(tool_use_block) -> dict:
    tool_function = TOOL_FUNCTIONS[tool_use_block.name]
    tool_result = tool_function(**tool_use_block.input)
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_block.id,
        "content": json.dumps(tool_result, default=str),
    }


def _extract_text(response) -> str:
    return "\n".join(block.text for block in response.content if block.type == "text")


if __name__ == "__main__":
    print("DC Metro Transit Assistant — type a question, or 'quit' to exit.")
    while True:
        try:
            question = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit"):
            print("Goodbye!")
            break

        try:
            answer = ask(question)
        except Exception as e:
            print(f"\n[Error] {e}")
            continue

        print(f"\nAssistant: {answer}")
