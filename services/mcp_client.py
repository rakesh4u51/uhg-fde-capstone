from fastmcp import Client

from mcp_servers.case_mcp.server import mcp as case_mcp
from mcp_servers.policy_mcp.server import mcp as policy_mcp
from mcp_servers.documents_mcp.server import mcp as documents_mcp
from mcp_servers.workflow_mcp.server import mcp as workflow_mcp


async def get_case(case_id: str) -> dict:
    async with Client(case_mcp) as client:
        result = await client.call_tool(
            "get_case",
            {"case_id": case_id},
        )

        return result.data


async def check_coverage(
    policy_number: str,
    claim_type: str,
    claim_amount: float,
) -> dict:

    async with Client(policy_mcp) as client:
        result = await client.call_tool(
            "check_coverage",
            {
                "policy_number": policy_number,
                "claim_type": claim_type,
                "claim_amount": claim_amount,
            },
        )

        return result.data


async def validate_documents(case_id: str) -> dict:
    async with Client(documents_mcp) as client:
        result = await client.call_tool(
            "validate_case_documents",
            {"case_id": case_id},
        )

        return result.data


async def request_human_approval(
    case_id: str,
    approver: str,
) -> dict:

    async with Client(workflow_mcp) as client:
        result = await client.call_tool(
            "request_approval",
            {
                "case_id": case_id,
                "approver": approver,
            },
        )

        return result.data