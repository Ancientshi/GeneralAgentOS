"""Provider-specific wire compatibility without changing stored conversations."""

from agno.models.openai import OpenAIChat


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
