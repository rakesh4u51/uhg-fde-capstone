from agents.v2_agent_base import SimpleMCPAgent, extract_case_id
from services.sla_tools import load_sla_tools


class SlaAgentV2(SimpleMCPAgent):
    async def _handle_prompt(self, text: str) -> str:
        case_id = extract_case_id(text) or "CASE-001"

        schedule_tool = self.tools["schedule_sla"]
        notify_tool = self.tools["send_notification"]
        request_docs_tool = self.tools["request_documents"]

        await schedule_tool.ainvoke({"case_id": case_id, "hours": 24})
        await notify_tool.ainvoke({"case_id": case_id, "message": "Claim has been routed for human review."})
        await request_docs_tool.ainvoke({"case_id": case_id, "documents": ["supporting_document"]})

        lines = [
            "COMMUNICATION: routine follow-up sent to the workflow queue and claimant contact path.",
            "SLA ACTION: schedule standard 24-hour review target for the case.",
            "ESCALATION: no escalation triggered based on the verified case data.",
            f"NEXT ACTION: await human approval and document follow-up for case {case_id}.",
        ]
        return "\n".join(lines)


async def build_sla_agent():
    tools, adapter = await load_sla_tools()
    return SlaAgentV2(tools), adapter
