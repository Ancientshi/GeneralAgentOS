import copy
import json

import pytest
from agno.models.message import Message
from agno.models.openai import OpenAIChat

from general_agent_os.models import VLLMChat
from general_agent_os.runtime import build_model


@pytest.mark.parametrize("arguments", ["", " \n", None])
def test_vllm_replays_zero_argument_tool_history_as_json_without_mutation(arguments):
    calls = [{"id": "call-1", "type": "function", "function": {
        "name": "list_benchmarks", "arguments": arguments,
    }}]
    original = copy.deepcopy(calls)
    message = Message(role="assistant", tool_calls=calls)
    wire = VLLMChat(id="test")._format_message(message)
    assert json.loads(wire["tool_calls"][0]["function"]["arguments"]) == {}
    assert message.tool_calls == original


@pytest.mark.parametrize("arguments", ['{"limit": 2}', "{malformed"])
def test_vllm_does_not_rewrite_nonempty_arguments(arguments):
    message = Message(role="assistant", tool_calls=[{
        "id": "call-1", "type": "function",
        "function": {"name": "search", "arguments": arguments},
    }])
    assert VLLMChat(id="test")._format_message(message)["tool_calls"][0]["function"]["arguments"] == arguments


def test_vllm_adapter_selection_and_provider_tool_metadata(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    model = build_model({"provider": "vllm", "model": "test", "base_url": "http://localhost:8000/v1"})
    assert isinstance(model, VLLMChat)
    assert model.provider == "VLLM"
    tools = [{"type": "function", "function": {
        "name": "list_benchmarks", "parameters": {"type": "object", "properties": {}},
        "requires_confirmation": False, "external_execution": False,
    }}]
    sent = model.get_request_params(tools=tools)["tools"][0]["function"]
    assert "requires_confirmation" not in sent and "external_execution" not in sent
    assert type(build_model({"provider": "openai", "model": "test"})) is OpenAIChat
