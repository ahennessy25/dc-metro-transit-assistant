"""Tests for the tool-dispatch and loop-termination mechanics in
agent/core.py. The Anthropic client is mocked entirely (no live API calls),
and TOOL_FUNCTIONS is replaced with fake functions (no real WMATA/weather/RAG
calls) — this only exercises ask()'s own logic: does it call the right
function with the right arguments, does it stop when it should, does it stop
when it's told to (the safety limit)?
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import agent.core as agent_core


@pytest.fixture(autouse=True)
def _fake_api_key(monkeypatch):
    """ask() now raises ConfigurationError up front when ANTHROPIC_API_KEY
    is falsy (see agent/core.py), independent of whatever the real
    environment/.env has set. These tests mock the client entirely, so they
    shouldn't depend on a real key being present — patch in a fake one.
    """
    monkeypatch.setattr(agent_core, "ANTHROPIC_API_KEY", "test-key")


def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(block_id, name, input):
    return SimpleNamespace(type="tool_use", id=block_id, name=name, input=input)


def _response(*blocks):
    return SimpleNamespace(content=list(blocks))


def _install_fake_client(monkeypatch, responses):
    """Replaces agent_core._client with a mock whose messages.create()
    returns each of `responses` in order, one per call.
    """
    fake_client = MagicMock()
    fake_client.messages.create = MagicMock(side_effect=responses)
    monkeypatch.setattr(agent_core, "_client", fake_client)
    return fake_client.messages.create


def test_no_tool_call_returns_text_immediately(monkeypatch):
    mock_create = _install_fake_client(monkeypatch, [_response(_text_block("42 minutes"))])
    fake_tool = MagicMock()
    monkeypatch.setattr(agent_core, "TOOL_FUNCTIONS", {"get_weather": fake_tool})

    result = agent_core.ask("what's 6 times 7")

    assert result == {"answer": "42 minutes", "tool_calls": []}
    assert mock_create.call_count == 1
    fake_tool.assert_not_called()


def test_single_tool_call_dispatches_correct_function_and_arguments(monkeypatch):
    tool_use = _tool_use_block("toolu_1", "get_weather", {"when": "now"})
    responses = [
        _response(tool_use),
        _response(_text_block("It's sunny.")),
    ]
    mock_create = _install_fake_client(monkeypatch, responses)

    fake_get_weather = MagicMock(return_value={"description": "Sunny", "temperature_f": 80})
    other_tool = MagicMock()
    monkeypatch.setattr(
        agent_core,
        "TOOL_FUNCTIONS",
        {"get_weather": fake_get_weather, "get_service_alerts": other_tool},
    )

    result = agent_core.ask("is it sunny")

    assert result["answer"] == "It's sunny."
    assert result["tool_calls"] == [{"name": "get_weather", "args": {"when": "now"}}]
    fake_get_weather.assert_called_once_with(when="now")
    other_tool.assert_not_called()

    # Verify the tool_result sent back on round 2 matches the tool's output
    # and references the correct tool_use_id.
    second_call_messages = mock_create.call_args_list[1].kwargs["messages"]
    tool_result_turn = second_call_messages[-1]
    assert tool_result_turn["role"] == "user"
    assert len(tool_result_turn["content"]) == 1
    tool_result_block = tool_result_turn["content"][0]
    assert tool_result_block["type"] == "tool_result"
    assert tool_result_block["tool_use_id"] == "toolu_1"
    assert tool_result_block["content"] == json.dumps({"description": "Sunny", "temperature_f": 80})


def test_multiple_tool_calls_in_one_response_dispatch_to_correct_functions(monkeypatch):
    weather_call = _tool_use_block("toolu_weather", "get_weather", {"when": "now"})
    alerts_call = _tool_use_block("toolu_alerts", "get_service_alerts", {"line": "RED"})
    responses = [
        _response(weather_call, alerts_call),
        _response(_text_block("Combined answer.")),
    ]
    mock_create = _install_fake_client(monkeypatch, responses)

    fake_get_weather = MagicMock(return_value={"description": "Cloudy"})
    fake_get_alerts = MagicMock(return_value=[{"cause": "MAINTENANCE"}])
    monkeypatch.setattr(
        agent_core,
        "TOOL_FUNCTIONS",
        {"get_weather": fake_get_weather, "get_service_alerts": fake_get_alerts},
    )

    result = agent_core.ask("weather and red line alerts?")

    assert result["answer"] == "Combined answer."
    assert result["tool_calls"] == [
        {"name": "get_weather", "args": {"when": "now"}},
        {"name": "get_service_alerts", "args": {"line": "RED"}},
    ]
    fake_get_weather.assert_called_once_with(when="now")
    fake_get_alerts.assert_called_once_with(line="RED")

    # Both tool_results should be present, each matched to the right call —
    # not swapped — via tool_use_id.
    second_call_messages = mock_create.call_args_list[1].kwargs["messages"]
    tool_result_blocks = {
        block["tool_use_id"]: block for block in second_call_messages[-1]["content"]
    }
    assert len(tool_result_blocks) == 2
    assert tool_result_blocks["toolu_weather"]["content"] == json.dumps({"description": "Cloudy"})
    assert tool_result_blocks["toolu_alerts"]["content"] == json.dumps([{"cause": "MAINTENANCE"}])


def test_sequential_tool_calls_across_multiple_rounds(monkeypatch):
    first_call = _tool_use_block("toolu_1", "get_weather", {"when": "now"})
    second_call = _tool_use_block("toolu_2", "get_service_alerts", {})
    responses = [
        _response(first_call),
        _response(second_call),
        _response(_text_block("Final answer after two rounds.")),
    ]
    mock_create = _install_fake_client(monkeypatch, responses)

    fake_get_weather = MagicMock(return_value={"description": "Rainy"})
    fake_get_alerts = MagicMock(return_value=[])
    monkeypatch.setattr(
        agent_core,
        "TOOL_FUNCTIONS",
        {"get_weather": fake_get_weather, "get_service_alerts": fake_get_alerts},
    )

    result = agent_core.ask("should I bike tomorrow")

    assert result["answer"] == "Final answer after two rounds."
    assert result["tool_calls"] == [
        {"name": "get_weather", "args": {"when": "now"}},
        {"name": "get_service_alerts", "args": {}},
    ]
    assert mock_create.call_count == 3
    fake_get_weather.assert_called_once_with(when="now")
    fake_get_alerts.assert_called_once_with()


def test_missing_api_key_raises_configuration_error_without_calling_client(monkeypatch):
    monkeypatch.setattr(agent_core, "ANTHROPIC_API_KEY", "")
    fake_client = MagicMock()
    monkeypatch.setattr(agent_core, "_client", fake_client)

    with pytest.raises(agent_core.ConfigurationError, match="ANTHROPIC_API_KEY"):
        agent_core.ask("when's the next train")

    fake_client.messages.create.assert_not_called()


def test_max_iterations_forces_final_call_without_tools(monkeypatch):
    # Claude keeps requesting the same tool forever — never returns a
    # text-only response within the tool-calling loop.
    def always_wants_a_tool(*args, **kwargs):
        return _response(_tool_use_block("toolu_x", "get_weather", {"when": "now"}))

    forced_final_response = _response(_text_block("Best effort answer."))

    call_count = {"n": 0}

    def create_side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] <= agent_core.MAX_TOOL_ITERATIONS:
            return always_wants_a_tool()
        return forced_final_response

    fake_client = MagicMock()
    fake_client.messages.create = MagicMock(side_effect=create_side_effect)
    monkeypatch.setattr(agent_core, "_client", fake_client)

    fake_get_weather = MagicMock(return_value={"description": "Foggy"})
    monkeypatch.setattr(agent_core, "TOOL_FUNCTIONS", {"get_weather": fake_get_weather})

    result = agent_core.ask("infinite loop question")

    assert result["answer"] == "Best effort answer."
    assert result["tool_calls"] == [
        {"name": "get_weather", "args": {"when": "now"}}
    ] * agent_core.MAX_TOOL_ITERATIONS
    # MAX_TOOL_ITERATIONS calls inside the loop + 1 forced final call.
    assert fake_client.messages.create.call_count == agent_core.MAX_TOOL_ITERATIONS + 1
    assert fake_get_weather.call_count == agent_core.MAX_TOOL_ITERATIONS

    # The forced final call must omit `tools`, or Claude could just ask
    # for another tool again instead of answering.
    final_call_kwargs = fake_client.messages.create.call_args_list[-1].kwargs
    assert "tools" not in final_call_kwargs
