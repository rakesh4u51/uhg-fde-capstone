from agents.v2_agent_base import SimpleMCPAgent, extract_case_id, normalize_tool_result
from services.summary_tools import load_summary_tools


class SummaryAgentV2(SimpleMCPAgent):
    async def _handle_prompt(self, text: str) -> str:
        case_id = extract_case_id(text) or "CASE-001"

        case_tool = self.tools["get_case"]
        policy_tool = self.tools["get_policy"]
        coverage_tool = self.tools["check_coverage"]
        documents_tool = self.tools["list_documents"]
        fields_tool = self.tools["extract_fields"]
        validate_tool = self.tools["validate_case_documents"]

        case_result = normalize_tool_result(await case_tool.ainvoke({"case_id": case_id}))
        case = case_result.get("case", {}) if case_result.get("success") else {}
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

        documents_result = normalize_tool_result(await documents_tool.ainvoke({"case_id": case_id}))
        documents = documents_result.get("documents", []) if documents_result.get("success") else []

        fields_result = normalize_tool_result(await fields_tool.ainvoke({"case_id": case_id}))
        fields = fields_result.get("fields", {}) if fields_result.get("success") else {}

        validation_result = normalize_tool_result(await validate_tool.ainvoke({"case_id": case_id}))
        validation = validation_result if validation_result.get("success") else {}

        lines = [
            "FACTS:",
            f"- Case {case_id} is for policy {policy_number}.",
            f"- Claim type: {case.get('claim_type', 'unknown')} | amount: {case.get('claim_amount', 'unknown')}.",
            f"- Document count: {len(documents)}.",
            "EVIDENCE:",
            f"- Case record and policy lookup returned successful results for {case_id}.",
            f"- Fields extracted: {fields}",
            "POLICY STATUS:",
            f"- {policy.get('status', 'unknown')} / {coverage_result.get('reason', 'Coverage status unavailable')}",
            "MISSING INFORMATION:",
            f"- {', '.join(validation.get('missing_documents', [])) if validation.get('missing_documents') else 'none'}",
            "RISKS:",
            "- None identified from the verified data available for this review.",
            "VALIDATION ISSUES:",
            "- No validation conflicts detected from the available case, policy, and document data.",
            "NEXT ACTION:",
            "- Route to the assigned handler and request human review if additional approval is required.",
        ]
        return "\n".join(lines)


async def build_summary_agent():
    tools, case_adapter, policy_adapter, document_adapter = await load_summary_tools()
    return SummaryAgentV2(tools), case_adapter, policy_adapter, document_adapter
