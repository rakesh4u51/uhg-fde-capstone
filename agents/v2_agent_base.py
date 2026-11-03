import json
import re
from typing import Any

from langchain_core.messages import AIMessage


CASE_ID_RE = re.compile(r"\b[A-Z]+-\d+\b")


def extract_case_id(text: str) -> str | None:
    if not text:
        return None
    match = CASE_ID_RE.search(text)
    if match:
        return match.group(0)
    return None


def normalize_tool_result(result: Any) -> Any:
    if isinstance(result, list):
        if result and isinstance(result[0], dict):
            payload = result[0].get("text")
            if isinstance(payload, str):
                try:
                    return json.loads(payload)
                except json.JSONDecodeError:
                    return payload
            return result[0]
        return result
    if isinstance(result, dict):
        return result
    return result


class SimpleMCPAgent:
    def __init__(self, tools: list[Any]):
        self.tools = {tool.name: tool for tool in tools}

    async def ainvoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        messages = payload.get("messages", [])
        if not messages:
            return {"messages": [AIMessage(content="No input supplied.")]}

        text = messages[-1].get("content", "") if isinstance(messages[-1], dict) else str(messages[-1])
        response = await self._handle_prompt(text)
        return {"messages": [AIMessage(content=response)]}

    async def _handle_prompt(self, text: str) -> str:
        raise NotImplementedError
