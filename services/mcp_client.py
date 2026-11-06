from __future__ import annotations

from typing import Any

from fastmcp import Client

from mcp_servers.case_mcp.server import mcp as case_mcp
from mcp_servers.documents_mcp.server import mcp as documents_mcp
from mcp_servers.policy_mcp.server import mcp as policy_mcp
from mcp_servers.workflow_mcp.server import mcp as workflow_mcp


def _coerce_tool_result(result: Any) -> dict[str, Any]:
    if result is None:
        raise RuntimeError("MCP call returned no result")
    if isinstance(result, dict):
        return result
    if hasattr(result, "data"):
        data = result.data
        if isinstance(data, dict):
            return data
        if data is None:
            raise RuntimeError("MCP call returned no structured data")
        return {"data": data}
    if hasattr(result, "model_dump"):
        payload = result.model_dump()
        if isinstance(payload, dict):
            return payload
    raise RuntimeError("MCP call returned an unexpected response shape")


async def _invoke_tool(server: Any, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    async with Client(server) as client:
        result = await client.call_tool(tool_name, arguments)
        payload = _coerce_tool_result(result)
        if payload.get("success") is False:
            raise RuntimeError(payload.get("error") or f"{tool_name} failed")
        return payload


async def get_case(case_id: str) -> dict:
    return await _invoke_tool(case_mcp, "get_case", {"case_id": case_id})


async def check_coverage(policy_number: str, claim_type: str, claim_amount: float) -> dict:
    return await _invoke_tool(
        policy_mcp,
        "check_coverage",
        {"policy_number": policy_number, "claim_type": claim_type, "claim_amount": claim_amount},
    )


async def validate_documents(case_id: str) -> dict:
    return await _invoke_tool(documents_mcp, "validate_case_documents", {"case_id": case_id})


async def request_human_approval(case_id: str, approver: str) -> dict:
    return await _invoke_tool(workflow_mcp, "request_approval", {"case_id": case_id, "approver": approver})