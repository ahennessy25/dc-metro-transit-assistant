"""Tests for _clean_history() in app.py — the conversion from Gradio's chat
history dicts into the plain {role, content} shape the Anthropic Messages API
accepts. Gradio's history entries carry extra keys (e.g. "metadata",
"options") that the API rejects with a 400 "Extra inputs are not permitted"
error if passed through unchanged, so this only exercises the stripping
logic in isolation — no live Anthropic API call, no ask() involved.
"""

from app import _clean_history


def test_strips_extra_keys_beyond_role_and_content():
    history = [
        {"role": "user", "content": "Is the Red Line running normally?", "metadata": None},
        {
            "role": "assistant",
            "content": "No active alerts.",
            "metadata": None,
            "options": None,
        },
    ]

    cleaned = _clean_history(history)

    assert cleaned == [
        {"role": "user", "content": "Is the Red Line running normally?"},
        {"role": "assistant", "content": "No active alerts."},
    ]
    for message in cleaned:
        assert set(message.keys()) == {"role", "content"}


def test_history_with_no_extra_keys_passes_through_unchanged():
    history = [
        {"role": "user", "content": "What about the Blue Line?"},
        {"role": "assistant", "content": "Running normally."},
    ]

    assert _clean_history(history) == history


def test_empty_history_returns_empty_list():
    assert _clean_history([]) == []


def test_preserves_role_and_content_order_and_values_across_multiple_turns():
    history = [
        {"role": "user", "content": "Is the Red Line running normally?", "metadata": None},
        {"role": "assistant", "content": "No active alerts.", "metadata": None},
        {"role": "user", "content": "What about the Blue Line?", "metadata": None},
        {"role": "assistant", "content": "Also running normally.", "metadata": None},
    ]

    cleaned = _clean_history(history)

    assert [m["role"] for m in cleaned] == ["user", "assistant", "user", "assistant"]
    assert [m["content"] for m in cleaned] == [
        "Is the Red Line running normally?",
        "No active alerts.",
        "What about the Blue Line?",
        "Also running normally.",
    ]
