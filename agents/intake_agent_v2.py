from agents.v2_agent_base import SimpleMCPAgent, extract_case_id, normalize_tool_result
from services.intake_tools import load_intake_tools


class IntakeAgentV2(SimpleMCPAgent):
    async def _handle_prompt(self, text: str) -> str:
        case_id = extract_case_id(text) or "CASE-001"

        case_tool = self.tools["get_case"]
        policy_tool = self.tools["get_policy"]
        coverage_tool = self.tools["check_coverage"]
        similar_tool = self.tools["find_similar_cases"]

        case_result = normalize_tool_result(await case_tool.ainvoke({"case_id": case_id}))
        if not case_result.get("success"):
            return f"I was unable to retrieve case {case_id}."

        case = case_result.get("case", {})
        policy_number = case.get("policy_number")

        policy_result = normalize_tool_result(await policy_tool.ainvoke({"policy_number": policy_number}))
        policy = policy_result.get("policy", {}) if policy_result.get("success") else {}

        coverage_result = normalize_tool_result(
            await coverage_tool.ainvoke(
                {
                    "policy_number": policy_number,
                    "claim_type": case.get("claim_type", ""),
                    "claim_amount": float(case.get("claim_amount", 0) or 0),
                }
            )
        )

        similar_result = normalize_tool_result(await similar_tool.ainvoke({"policy_number": policy_number}))
        similar_cases = similar_result.get("cases", []) if similar_result.get("success") else []

        lines = [
            f"CASE: {case_id}",
            f"POLICY: {policy_number}",
            f"CLAIM TYPE: {case.get('claim_type', 'unknown')}",
            f"CLAIM AMOUNT: {case.get('claim_amount', 'unknown')}",
            f"COVERAGE: {coverage_result.get('reason', 'Coverage status unavailable')}",
            f"SIMILAR CASES: {len(similar_cases) if isinstance(similar_cases, list) else 0}",
            f"POLICY STATUS: {policy.get('status', 'unknown')}",
            "NEXT STEP: continue with manual review and request any missing intake information before approval.",
        ]

        return "\n".join(lines)


async def build_intake_agent():
    tools, case_adapter, policy_adapter = await load_intake_tools()
    return IntakeAgentV2(tools), case_adapter, policy_adapter
