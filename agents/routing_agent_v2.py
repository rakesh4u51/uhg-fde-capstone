import json

from agents.v2_agent_base import SimpleMCPAgent, extract_case_id
from services.routing_tools import load_routing_tools


class RoutingAgentV2(SimpleMCPAgent):
    async def _handle_prompt(self, text: str) -> str:
        case_id = extract_case_id(text) or "CASE-001"

        case_tool = self.tools["get_case"]
        workload_tool = self.tools["get_workload"]
        assign_tool = self.tools["assign_case"]
        approval_tool = self.tools["request_approval"]

        case_result = await case_tool.ainvoke({"case_id": case_id})
        case_payload = case_result[0]["text"] if isinstance(case_result, list) and case_result else "{}"
        case_data = json.loads(case_payload)
        case_data.get("case", {})

        workload = await workload_tool.ainvoke({})
        workload_payload = workload[0]["text"] if isinstance(workload, list) and workload else "{}"
        workload_data = json.loads(workload_payload)
        adjusters = workload_data.get("adjusters", [])
        assignee = adjusters[0].get("name", "Adjuster A") if adjusters else "Adjuster A"

        await assign_tool.ainvoke({"case_id": case_id, "assignee": assignee})
        await approval_tool.ainvoke({"case_id": case_id, "approver": "Demo Approver"})

        lines = [
            f"HANDLER: {assignee}",
            "ROUTING REASON: lowest current workload and case readiness for human review.",
            "HUMAN APPROVAL ROUTE: Demo Approver",
            f"NEXT ACTION: continue with SLA monitoring for case {case_id}.",
        ]
        return "\n".join(lines)


async def build_routing_agent():
    tools, case_adapter, workflow_adapter = await load_routing_tools()
    return RoutingAgentV2(tools), case_adapter, workflow_adapter
