import asyncio

import pytest
from fastmcp import Client

from mcp_servers.case_mcp.server import mcp as case_mcp
from mcp_servers.policy_mcp.server import mcp as policy_mcp
from mcp_servers.documents_mcp.server import mcp as documents_mcp
from mcp_servers.workflow_mcp.server import mcp as workflow_mcp
from services.document_tools import ALLOWED_DOCUMENT_TOOLS
from services.intake_tools import ALLOWED_INTAKE_TOOLS
from services.routing_tools import ALLOWED_ROUTING_TOOLS
from services.sla_tools import ALLOWED_SLA_TOOLS
from services.summary_tools import ALLOWED_SUMMARY_TOOLS


def test_case_mcp():
    async def _run():
        async with Client(case_mcp) as client:
            tools = await client.list_tools()
            tool_names = {tool.name for tool in tools}
            assert {"get_case", "list_cases", "register_case", "find_similar_cases", "save_summary", "get_case_timeline"}.issubset(tool_names)
            result = await client.call_tool("get_case", {"case_id": "CASE-001"})
            assert result.data["success"] is True

    asyncio.run(_run())


def test_policy_mcp():
    async def _run():
        async with Client(policy_mcp) as client:
            tools = await client.list_tools()
            tool_names = {tool.name for tool in tools}
            assert {"get_policy", "check_coverage", "search_policy_wording"}.issubset(tool_names)
            result = await client.call_tool("check_coverage", {"policy_number": "POL-1001", "claim_type": "Medical", "claim_amount": 25000})
            payload = result.data
            assert payload["success"] is True
            assert payload["covered"] is True

    asyncio.run(_run())


def test_policy_search_wording_like_hospital_treatment():
    async def _run():
        async with Client(policy_mcp) as client:
            result = await client.call_tool(
                "search_policy_wording",
                {"query": "Is inpatient hospital treatment covered?", "policy_number": "POL-1001"},
            )
            payload = result.data
            assert payload["success"] is True
            assert payload["policy_number"] == "POL-1001"
            assert "Medical" in str(payload.get("matching_policy_clause", "")) or payload.get("source")

            no_match = await client.call_tool("search_policy_wording", {"query": "This query is not related to any policy", "policy_number": "POL-999"})
            assert no_match.data["success"] is False or no_match.data["matches"] == []

    asyncio.run(_run())


def test_documents_mcp():
    async def _run():
        async with Client(documents_mcp) as client:
            tools = await client.list_tools()
            tool_names = {tool.name for tool in tools}
            assert {"list_documents", "extract_text", "classify_document", "extract_fields", "validate_case_documents"}.issubset(tool_names)
            result = await client.call_tool("validate_case_documents", {"case_id": "CASE-001"})
            payload = result.data
            assert payload["success"] is True
            assert payload["continue_allowed"] is True

    asyncio.run(_run())


def test_workflow_mcp():
    async def _run():
        async with Client(workflow_mcp) as client:
            tools = await client.list_tools()
            tool_names = {tool.name for tool in tools}
            assert {"get_workload", "assign_case", "request_approval", "schedule_sla", "send_notification", "request_documents"}.issubset(tool_names)
            result = await client.call_tool("request_approval", {"case_id": "CASE-001", "approver": "Demo Approver"})
            assert result.data["success"] is True

    asyncio.run(_run())


def test_specialist_tool_access_is_least_privilege():
    assert ALLOWED_INTAKE_TOOLS == {"get_case", "register_case", "find_similar_cases", "get_policy", "check_coverage"}
    assert ALLOWED_DOCUMENT_TOOLS == {"list_documents", "extract_text", "classify_document", "extract_fields", "validate_case_documents"}
    assert ALLOWED_SUMMARY_TOOLS >= {"get_case", "get_policy", "check_coverage", "save_summary"}
    assert ALLOWED_ROUTING_TOOLS >= {"get_workload", "assign_case", "request_approval"}
    assert ALLOWED_SLA_TOOLS == {"schedule_sla", "send_notification", "request_documents"}

    prohibited = {"approve_claim", "reject_claim", "settle_claim"}
    assert not prohibited & ALLOWED_INTAKE_TOOLS
    assert not prohibited & ALLOWED_DOCUMENT_TOOLS
    assert not prohibited & ALLOWED_SUMMARY_TOOLS
    assert not prohibited & ALLOWED_ROUTING_TOOLS
    assert not prohibited & ALLOWED_SLA_TOOLS


def main():
    test_case_mcp()
    test_policy_mcp()
    test_policy_search_wording_like_hospital_treatment()
    test_documents_mcp()
    test_workflow_mcp()
    test_specialist_tool_access_is_least_privilege()
    print("ALL MCP TESTS COMPLETED")


if __name__ == "__main__":
    main()