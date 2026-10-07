"""Provider-specific wire compatibility without changing stored conversations."""

from agno.exceptions import ModelProviderError
from agno.models.message import Message
from agno.models.openai import OpenAIChat, OpenAIResponses


class VLLMChat(OpenAIChat):
    def _format_message(self, message, compress_tool_results=False):
        result = super()._format_message(message, compress_tool_results)
        calls = result.get("tool_calls")
        if calls:
            normalized = []
            for call in calls:
                function = call.get("function")
                if isinstance(function, dict):
                    arguments = function.get("arguments")
                    # Some streaming tool parsers emit an empty argument string
                    # for zero-argument calls. vLLM parses history as JSON and
                    # rejects that string on the next model request.
                    if arguments is None or (isinstance(arguments, str) and not arguments.strip()):
                        call = {**call, "function": {**function, "arguments": "{}"}}
                normalized.append(call)
            result["tool_calls"] = normalized
        return result


class StreamingOnlyResponses(OpenAIResponses):
    """Use a streaming-only Responses gateway for both streaming and regular runs."""

    def _request(self, messages, response_format, tools, tool_choice, run_response, compress_tool_results):
        params = self.get_request_params(
            messages=messages,
            response_format=response_format,
            tools=tools,
            tool_choice=tool_choice,
            run_response=run_response,
        )
        params.pop("background", None)
        params.pop("stream", None)
        return {
            **self._get_model_request_kwargs(),
            "input": self._format_messages(messages, compress_tool_results, tools=tools),
            "stream": True,
            **params,
        }

    def _consume_event(self, event, state):
        delta, state["tool_use"] = self._parse_provider_response_delta(
            event, state["message"], state["tool_use"]
        )
        if delta.content:
            state["content"].append(delta.content)
        if delta.tool_calls:
            state["tool_calls"].extend(delta.tool_calls)
        if event.type == "response.completed":
            state["completed"] = event.response

    def _finish(self, state, response_format):
        completed = state["completed"]
        if completed is None:
            raise ModelProviderError(message="Responses stream ended without completion", model_name=self.name, model_id=self.id)
        result = self._parse_provider_response(completed, response_format=response_format)
        if not result.content and state["content"]:
            result.content = "".join(state["content"])
        if not result.tool_calls and state["tool_calls"]:
            result.tool_calls = state["tool_calls"]
            result.extra = result.extra or {}
            result.extra["tool_call_ids"] = [call["call_id"] for call in state["tool_calls"]]
        return result

    @staticmethod
    def _state():
        return {"message": Message(role="assistant"), "tool_use": {}, "content": [], "tool_calls": [], "completed": None}

    def invoke(
        self, messages, assistant_message, response_format=None, tools=None,
        tool_choice=None, run_response=None, compress_tool_results=False,
    ):
        assistant_message.metrics.start_timer()
        state = self._state()
        try:
            for event in self.get_client().responses.create(
                **self._request(messages, response_format, tools, tool_choice, run_response, compress_tool_results)
            ):
                self._consume_event(event, state)
        finally:
            assistant_message.metrics.stop_timer()
        return self._finish(state, response_format)

    async def ainvoke(
        self, messages, assistant_message, response_format=None, tools=None,
        tool_choice=None, run_response=None, compress_tool_results=False,
    ):
        assistant_message.metrics.start_timer()
        state = self._state()
        try:
            stream = await self.get_async_client().responses.create(
                **self._request(messages, response_format, tools, tool_choice, run_response, compress_tool_results)
            )
            async for event in stream:
                self._consume_event(event, state)
        finally:
            assistant_message.metrics.stop_timer()
        return self._finish(state, response_format)
