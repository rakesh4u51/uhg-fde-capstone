from agents.v2_agent_base import SimpleMCPAgent, extract_case_id, normalize_tool_result
from services.document_tools import load_document_tools


class DocumentAgentV2(SimpleMCPAgent):
    async def _handle_prompt(self, text: str) -> str:
        case_id = extract_case_id(text) or "CASE-001"

        list_tool = self.tools["list_documents"]
        text_tool = self.tools["extract_text"]
        classify_tool = self.tools["classify_document"]
        fields_tool = self.tools["extract_fields"]
        validate_tool = self.tools["validate_case_documents"]

        documents_result = normalize_tool_result(await list_tool.ainvoke({"case_id": case_id}))
        documents = documents_result.get("documents", []) if documents_result.get("success") else []

        extracted_result = normalize_tool_result(await text_tool.ainvoke({"case_id": case_id}))
        extracted = extracted_result.get("results", []) if extracted_result.get("success") else []

        classifications_result = normalize_tool_result(await classify_tool.ainvoke({"case_id": case_id}))
        classifications = classifications_result.get("classifications", []) if classifications_result.get("success") else []

        fields_result = normalize_tool_result(await fields_tool.ainvoke({"case_id": case_id}))
        fields = fields_result.get("fields", {}) if fields_result.get("success") else {}

        validation_result = normalize_tool_result(await validate_tool.ainvoke({"case_id": case_id}))
        validation = validation_result if validation_result.get("success") else {}

        doc_type = classifications[0].get("document_type", "unknown") if classifications else "unknown"
        confidence = extracted[0].get("confidence", 0) if extracted else 0
        missing = validation.get("missing_documents", [])

        lines = [
            f"DOCUMENT TYPE: {doc_type}",
            f"FACTS: {', '.join(d.get('text', '') for d in extracted) if extracted else 'No extracted text available'}",
            f"MISSING INFORMATION: {', '.join(missing) if missing else 'none'}",
            f"RISKS: {'none' if not missing else 'document validation incomplete'}",
            f"CONFIDENCE: {confidence}",
            "NEXT ACTION: continue review with the available evidence and request missing documents if required.",
        ]
        return "\n".join(lines)


async def build_document_agent():
    tools, adapter = await load_document_tools()
    return DocumentAgentV2(tools), adapter
