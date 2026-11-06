from agents.v2_agent_base import SimpleMCPAgent, extract_case_id, normalize_tool_result
from services.summary_tools import load_summary_tools


def build_grounded_summary(
    case_id: str,
    case: dict | None,
    policy: dict | None,
    coverage: dict | None,
    documents: list[dict] | None,
    fields: dict | None,
    validation: dict | None,
) -> str:
    case = case or {}
    policy = policy or {}
    coverage = coverage or {}
    documents = documents or []
    fields = fields or {}
    validation = validation or {}

    policy_number = str(policy.get("policy_number") or case.get("policy_number") or "unknown")
    claim_type = str(case.get("claim_type") or fields.get("claim_type") or "unknown")
    claim_amount = case.get("claim_amount", "unknown")
    policy_status = str(policy.get("status") or "unknown")
    coverage_limit = policy.get("coverage_limit", "unknown")
    covered_types = policy.get("covered_claim_types") or []
    if isinstance(covered_types, str):
        covered_types = [covered_types]
    covered_types_text = ", ".join(str(item) for item in covered_types) if covered_types else "not specified"
    coverage_reason = str(coverage.get("reason") or "Coverage status unavailable")
    coverage_value = "covered" if coverage.get("covered") is True else "not covered" if coverage.get("covered") is False else "status unavailable"
    missing_documents = validation.get("missing_documents") or []
    risks = validation.get("risks") or validation.get("validation_issues") or []
    issues = validation.get("issues") or validation.get("validation_issues") or []

    lines = [
        "FACTS:",
        f"- Claim {case_id} is associated with policy {policy_number}.",
        f"- Claim type: {claim_type} | amount: {claim_amount}.",
        f"- Verified document count: {len(documents)}.",
        "EVIDENCE:",
        f"- Case data retrieved successfully for {case_id}.",
        f"- Extracted fields: {fields if fields else 'none'}.",
        f"- Document types reviewed: {', '.join(str(doc.get('document_type') or 'unknown') for doc in documents) if documents else 'none'}.",
        "POLICY AND COVERAGE:",
        f"- Policy status: {policy_status}",
        f"- Coverage result: {coverage_value} ({coverage_reason})",
        f"- Coverage limit: {coverage_limit}",
        f"- Covered claim types: {covered_types_text}",
        "MISSING INFORMATION:",
        f"- {', '.join(str(item) for item in missing_documents) if missing_documents else 'none'}",
        "RISKS:",
        f"- {', '.join(str(item) for item in risks) if risks else 'none identified from verified data'}",
        "NEXT ACTION:",
        "- Route this case to the assigned handler and request human review for the final decision.",
        "Policy References:",
        f"- source: case policy record / policy_number={policy_number} / status={policy_status} / coverage_limit={coverage_limit} / covered_types={covered_types_text}",
    ]

    if issues:
        lines.insert(len(lines) - 2, "VALIDATION ISSUES:")
        lines.insert(len(lines) - 1, f"- {', '.join(str(item) for item in issues)}")

    return "\n".join(lines)


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

        return build_grounded_summary(
            case_id=case_id,
            case=case,
            policy=policy,
            coverage=coverage_result,
            documents=documents,
            fields=fields,
            validation=validation,
        )


async def build_summary_agent():
    tools, case_adapter, policy_adapter, document_adapter = await load_summary_tools()
    return SummaryAgentV2(tools), case_adapter, policy_adapter, document_adapter
