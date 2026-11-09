from types import SimpleNamespace

from langgraph.types import Command

import graph.workflow_v2 as workflow
from app import streamlit_app
from services.audit import record_audit
from services.database import get_connection
from services.document_processor import save_document_result


def test_case_status_aliases_are_canonicalized():
    assert streamlit_app._canonical_case_status("awaiting_documents2") == "awaiting_documents"
    assert streamlit_app._canonical_case_status("documents_waiting") == "awaiting_documents"
    assert workflow._canonical_status("awaiting_document") == "awaiting_documents"


def test_resume_existing_case_document_reuses_thread(monkeypatch):
    class FakeGraph:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def aget_state(self, config):
            return SimpleNamespace(
                values={
                    "case_id": "CASE-RESUME",
                    "current_stage": "awaiting_documents",
                    "status": "awaiting_documents",
                    "claim_data": {"case_id": "CASE-RESUME"},
                }
            )

        async def ainvoke(self, command, config):
            assert config["configurable"]["thread_id"] == "CASE-RESUME-THREAD"
            assert command.resume["document_id"].startswith("DOC-")
            assert command.resume["document_type"] == "medical_bill"
            return {"status": "documents_revalidated", "current_stage": "documents_revalidated"}

    monkeypatch.setattr(streamlit_app, "_get_thread_id", lambda case_id, create_if_missing=False: "CASE-RESUME-THREAD")
    monkeypatch.setattr(
        streamlit_app,
        "process_document",
        lambda path: SimpleNamespace(
            extracted_text="Hospital bill total 25000",
            document_type="medical_bill",
            confidence=0.96,
            injection_detected=False,
        ),
    )
    monkeypatch.setattr(
        streamlit_app,
        "save_document_result",
        lambda case_id, path, document_id=None, result=None: {
            "document_id": document_id,
            "extracted_text": result.extracted_text,
            "document_type": result.document_type,
            "confidence": result.confidence,
        },
    )
    monkeypatch.setattr(streamlit_app, "get_v2_graph", lambda: FakeGraph())

    uploaded = SimpleNamespace(name="medical_bill.pdf", getvalue=lambda: b"demo")
    result = streamlit_app._resume_existing_case_documents("CASE-RESUME", [uploaded])

    assert result["status"] == "documents_revalidated"
    assert result["current_stage"] == "documents_revalidated"


def test_resume_existing_case_document_allows_processing_state(monkeypatch):
    class FakeGraph:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def aget_state(self, config):
            return SimpleNamespace(
                values={
                    "case_id": "CASE-RESUME-PROCESSING",
                    "current_stage": "documents_processing",
                    "status": "documents_processing",
                    "claim_data": {"case_id": "CASE-RESUME-PROCESSING"},
                }
            )

        async def ainvoke(self, command, config):
            assert config["configurable"]["thread_id"] == "CASE-RESUME-PROCESSING-THREAD"
            assert command.resume["document_type"] == "medical_bill"
            return {"status": "documents_revalidated", "current_stage": "documents_revalidated"}

    monkeypatch.setattr(streamlit_app, "_get_thread_id", lambda case_id, create_if_missing=False: "CASE-RESUME-PROCESSING-THREAD")
    monkeypatch.setattr(
        streamlit_app,
        "process_document",
        lambda path: SimpleNamespace(
            extracted_text="Replacement evidence accepted",
            document_type="medical_bill",
            confidence=0.91,
            injection_detected=False,
        ),
    )
    monkeypatch.setattr(
        streamlit_app,
        "save_document_result",
        lambda case_id, path, document_id=None, result=None: {
            "document_id": document_id,
            "extracted_text": result.extracted_text,
            "document_type": result.document_type,
            "confidence": result.confidence,
        },
    )
    monkeypatch.setattr(streamlit_app, "get_v2_graph", lambda: FakeGraph())

    uploaded = SimpleNamespace(name="resume_document.pdf", getvalue=lambda: b"demo")
    result = streamlit_app._resume_existing_case_documents("CASE-RESUME-PROCESSING", [uploaded])

    assert result["status"] == "documents_revalidated"
    assert result["current_stage"] == "documents_revalidated"


def test_human_review_requires_explicit_decision_before_finalization(monkeypatch):
    monkeypatch.setattr(
        workflow,
        "interrupt",
        lambda payload: {"decision": "unknown", "reviewer": "Demo Approver", "rationale": "Still waiting"},
    )
    state = {
        "case_id": "CASE-HUMAN-PENDING",
        "current_stage": "awaiting_human_review",
        "status": "awaiting_human_review",
        "summary_result": "Summary",
        "routing_result": "Routing",
    }

    result = workflow.human_review_node(state)

    assert result["status"] == "awaiting_human_review"
    assert result["current_stage"] == "awaiting_human_review"
    assert result["human_decision"] == ""


def test_await_documents_resume_targets_latest_document_id(monkeypatch):
    monkeypatch.setattr(workflow, "interrupt", lambda payload: {"document_id": "DOC-NEW", "document_text": "Claimant Name: Demo Customer\nPolicy Number: POL-1001\nAmount: 25000\nService Date: 2026-10-20", "document_type": "medical_bill", "document_confidence": 0.98})
    state = {
        "case_id": "CASE-REVALIDATE-LATEST",
        "claim_data": {"claim_type": "Medical", "claim_amount": 25000.0},
        "current_stage": "awaiting_documents",
        "status": "awaiting_documents",
        "missing_documents": ["medical_bill"],
        "document_ids": ["DOC-OLD", "DOC-NEW"],
    }

    result = workflow.await_documents_node(state)

    assert isinstance(result, Command)
    assert result.update["document_ids"] == ["DOC-NEW"]
    assert result.update["status"] == "documents_revalidated"
    assert result.update["current_stage"] == "documents_revalidated"


def test_await_documents_resume_continues_when_uploaded_document_has_blank_text(monkeypatch):
    monkeypatch.setattr(workflow, "interrupt", lambda payload: {"document_id": "DOC-BLANK", "document_text": "", "document_type": "supporting_document", "document_confidence": 0.0})
    state = {
        "case_id": "CASE-REVALIDATE-BLANK-TEXT",
        "claim_data": {"claim_type": "Medical", "claim_amount": 25000.0},
        "current_stage": "awaiting_documents",
        "status": "awaiting_documents",
        "missing_documents": ["medical_bill"],
        "document_ids": ["DOC-OLD"],
    }

    result = workflow.await_documents_node(state)

    assert isinstance(result, Command)
    assert result.goto == "documents"
    assert result.update["document_ids"] == ["DOC-BLANK"]
    assert result.update["status"] == "documents_revalidated"
    assert result.update["current_stage"] == "documents_revalidated"


def test_resume_paths_clear_stale_document_blockers(monkeypatch):
    monkeypatch.setattr(
        workflow,
        "interrupt",
        lambda payload: {"action": "continue_processing", "reviewer": "Demo Approver", "rationale": "Resolved", "resolved_risks": ["low_confidence"]},
    )
    manual_state = {
        "case_id": "CASE-RESUME-MANUAL",
        "current_stage": "manual_review",
        "status": "manual_review",
        "risks": ["low_confidence"],
        "missing_documents": ["medical_bill"],
        "document_complete": True,
        "continue_allowed": True,
        "document_validation": {"missing_documents": ["medical_bill"], "continue_allowed": True, "complete": True},
        "security_flags": [],
    }

    manual_result = workflow.manual_review_node(manual_state)
    assert isinstance(manual_result, Command)
    assert manual_result.update["missing_documents"] == []
    assert manual_result.update["document_validation"]["missing_documents"] == []
    assert manual_result.update["document_complete"] is False
    assert manual_result.update["continue_allowed"] is False

    monkeypatch.setattr(workflow, "interrupt", lambda payload: {"document_id": "DOC-RESUME", "document_text": "Hospital bill total 25000", "document_type": "medical_bill", "document_confidence": 0.98})
    await_state = {
        "case_id": "CASE-RESUME-AWAIT",
        "claim_data": {"claim_type": "Medical", "claim_amount": 25000.0},
        "current_stage": "awaiting_documents",
        "status": "awaiting_documents",
        "missing_documents": ["medical_bill"],
        "document_complete": False,
        "continue_allowed": False,
        "document_validation": {"missing_documents": ["medical_bill"], "continue_allowed": False, "complete": False},
    }

    await_result = workflow.await_documents_node(await_state)
    assert isinstance(await_result, Command)
    assert await_result.update["missing_documents"] == []
    assert await_result.update["document_validation"]["missing_documents"] == []
    assert await_result.update["continue_allowed"] is False


def test_await_documents_node_persists_status_before_interrupt(monkeypatch):
    calls = []
    monkeypatch.setattr(workflow, "interrupt", lambda payload: {"document_id": "DOC-NEW", "document_text": "Claimant Name: Demo Customer\nPolicy Number: POL-1001\nAmount: 25000\nService Date: 2026-10-20", "document_type": "medical_bill", "document_confidence": 0.98})
    monkeypatch.setattr(workflow, "_persist_case_status", lambda case_id, status, stage: calls.append((case_id, status, stage)))
    state = {
        "case_id": "CASE-AWAIT-STATUS",
        "claim_data": {"claim_type": "Medical", "claim_amount": 25000.0},
        "missing_documents": ["medical_bill"],
    }

    workflow.await_documents_node(state)

    assert ("CASE-AWAIT-STATUS", "awaiting_documents", "awaiting_documents") in calls


def test_document_fan_out_marks_processing_stage():
    state = {
        "case_id": "CASE-DOC-FAN-OUT",
        "claim_data": {"claim_type": "Medical", "claim_amount": 25000.0},
        "document_ids": ["DOC-LOOP-001", "DOC-LOOP-002"],
        "current_stage": "intake_complete",
    }

    result = workflow.document_node(state)

    assert isinstance(result, Command)
    assert result.update["current_stage"] == "documents_processing"
    assert result.update["status"] == "documents_processing"


def test_repeated_document_stage_routes_to_manual_review():
    state = {
        "case_id": "CASE-REPEATED-DOC-STAGE",
        "current_stage": "documents_processing",
        "document_results": [
            {
                "document_id": "DOC-REPEAT-1",
                "document_type": "medical_bill",
                "confidence": 0.8,
                "processing_complete": True,
                "risks": [],
                "security_flags": [],
                "validation_issues": [],
            }
        ],
        "document_complete": False,
        "status": "documents_processing",
    }

    result = workflow.supervisor_node(state)

    assert isinstance(result, Command)
    assert result.goto == "manual_review"
    assert "Invalid repeated document stage" in result.update["supervisor_reason"]


def test_clean_medical_bill_worker_does_not_fail_on_optional_fields():
    case_id = "CASE-OPTIONAL-FIELDS"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO public.claims (case_id, policy_number, claimant_name, claim_type, claim_amount, status, description, summary) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (case_id) DO NOTHING",
                (case_id, "POL-1001", "Test Customer", "Medical", 25000.0, "new", "test claim", "test summary"),
            )
            cur.execute(
                "INSERT INTO public.documents (document_id, case_id, file_name, document_type, extracted_text, confidence, injection_detected) VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (document_id) DO NOTHING",
                (f"DOC-{case_id}", case_id, "medical_bill.pdf", "medical_bill", "Hospital bill. Total amount 25000.", 0.98, False),
            )
        conn.commit()

    result = workflow._process_document_worker_result(
        case_id,
        f"DOC-{case_id}",
        {"claimant_name": "Test Customer", "policy_number": "POL-1001", "claim_amount": 25000.0},
    )

    assert result["processing_complete"] is True
    assert result["complete"] is True


def test_clean_medical_bill_aggregation_uses_processing_complete():
    state = {
        "case_id": "CASE-AGG-CLEAN",
        "claim_data": {"claim_type": "Medical", "claim_amount": 25000.0},
        "document_ids": ["DOC-A15C2BD6"],
        "document_results": [
            {
                "document_id": "DOC-A15C2BD6",
                "document_type": "medical_bill",
                "confidence": 0.8,
                "complete": False,
                "processing_complete": True,
                "risks": [],
                "security_flags": [],
                "validation_issues": [],
            }
        ],
    }

    result = workflow.document_aggregation_node(state)

    assert result["document_complete"] is True
    assert result["missing_documents"] == []
    assert result["document_validation"]["continue_allowed"] is True
    assert result["document_validation"]["document_types"] == ["medical_bill"]


def test_missing_medical_bill_routes_to_await_documents():
    state = {
        "case_id": "CASE-MISSING-MEDICAL",
        "claim_data": {"claim_type": "Medical", "claim_amount": 25000.0},
        "document_ids": [],
        "document_results": [],
    }

    result = workflow.document_aggregation_node(state)

    assert result["missing_documents"] == ["medical_bill"]
    assert result["document_complete"] is False
    assert result["document_validation"]["continue_allowed"] is False


def test_processed_unknown_document_type_does_not_keep_case_awaiting_documents():
    state = {
        "case_id": "CASE-UNKNOWN-DOC-TYPE",
        "claim_data": {"claim_type": "Medical", "claim_amount": 25000.0},
        "document_ids": ["DOC-UNKNOWN"],
        "document_results": [
            {
                "document_id": "DOC-UNKNOWN",
                "document_type": "unknown",
                "confidence": 0.91,
                "complete": True,
                "processing_complete": True,
                "risks": [],
                "security_flags": [],
                "validation_issues": [],
            }
        ],
    }

    result = workflow.document_aggregation_node(state)

    assert result["missing_documents"] == []
    assert result["document_complete"] is True
    assert result["document_validation"]["continue_allowed"] is True


def test_low_confidence_document_requires_manual_review():
    state = {
        "case_id": "CASE-LOW-CONFIDENCE",
        "claim_data": {"claim_type": "Medical", "claim_amount": 25000.0},
        "document_ids": ["DOC-LOW-CONF"],
        "document_results": [
            {
                "document_id": "DOC-LOW-CONF",
                "document_type": "medical_bill",
                "confidence": 0.5,
                "processing_complete": True,
                "risks": ["low_confidence"],
                "security_flags": [],
                "validation_issues": ["Low confidence extraction requires manual review."],
            }
        ],
    }

    result = workflow.document_aggregation_node(state)

    assert result["document_complete"] is True
    assert result["document_validation"]["continue_allowed"] is False
    assert "low_confidence" in result["risks"]


def test_prompt_injection_document_requires_manual_review():
    state = {
        "case_id": "CASE-INJECTION",
        "claim_data": {"claim_type": "Medical", "claim_amount": 25000.0},
        "document_ids": ["DOC-INJECTION"],
        "document_results": [
            {
                "document_id": "DOC-INJECTION",
                "document_type": "medical_bill",
                "confidence": 0.9,
                "processing_complete": True,
                "risks": ["prompt_injection_detected"],
                "security_flags": ["prompt_injection_detected"],
                "validation_issues": ["Prompt injection detected; document handling was restricted."],
            }
        ],
    }

    result = workflow.document_aggregation_node(state)

    assert result["document_complete"] is True
    assert result["document_validation"]["continue_allowed"] is False
    assert "prompt_injection_detected" in result["risks"]


def test_hydrate_claim_data_preserves_extracted_text():
    case_id = "CASE-HYDRATE-TEXT"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM public.claims WHERE case_id = %s",
                (case_id,),
            )
            if cur.fetchone() is None:
                cur.execute(
                    """
                    INSERT INTO public.claims (
                        case_id,
                        policy_number,
                        claimant_name,
                        claim_type,
                        claim_amount,
                        description,
                        status
                    ) VALUES (%s, %s, %s, %s, %s, %s, 'submitted')
                    """,
                    (case_id, "POL-1001", "Test Customer", "Medical", 25000.0, "hydration check",),
                )
            conn.commit()

    saved = save_document_result(
        case_id,
        file_path="/tmp/hydration_document.txt",
        document_id="DOC-HYDRATE-TEXT",
        result=type(
            "DocResult",
            (),
            {
                "document_type": "medical_bill",
                "extracted_text": "Claimant Name: Test Customer\nAmount: $25,000\nHospital bill",
                "confidence": 0.95,
                "injection_detected": False,
            },
        )(),
    )

    hydrated = streamlit_app._hydrate_claim_data(case_id, {"case_id": case_id})

    assert saved["extracted_text"] == "Claimant Name: Test Customer\nAmount: $25,000\nHospital bill"
    assert hydrated["document_text"] == "Claimant Name: Test Customer\nAmount: $25,000\nHospital bill"


def test_clean_claim_routes_to_summary():
    state = {
        "case_id": "CASE-100",
        "current_stage": "documents_complete",
        "document_complete": True,
        "missing_documents": [],
        "document_validation": {"continue_allowed": True},
        "risks": [],
        "errors": [],
    }

    result = workflow.supervisor_node(state)

    assert isinstance(result, Command)
    assert result.goto == "summary"
    assert result.update["next_step"] == "summary"


def test_phase_completion_updates_stage_and_status():
    state = {"case_id": "CASE-STAGE-SET"}

    intake = workflow.intake_node(state)
    assert intake["current_stage"] == "intake_complete"
    assert intake["status"] == "intake_complete"

    summary = workflow.summary_node({**state, "risks": [], "missing_documents": []})
    assert summary["current_stage"] == "summary_complete"
    assert summary["status"] == "summary_complete"

    routing = workflow.routing_node({**state})
    assert routing["current_stage"] == "routing_complete"
    assert routing["status"] == "routing_complete"

    sla = workflow.sla_node({**state})
    assert sla["current_stage"] == "sla_complete"
    assert sla["status"] == "sla_complete"


def test_vehicle_claim_missing_documents_are_specific_to_the_claim_type():
    state = {
        "case_id": "CASE-VEHICLE-001",
        "claim_data": {"claim_type": "Vehicle", "document_text": "", "document_confidence": 0.0},
    }

    result = workflow.document_node(state)

    assert result["missing_documents"] == ["accident_report", "repair_estimate"]


def test_claimant_and_amount_mismatch_block_workflow_continuation():
    case_id = "CASE-MISMATCH-001"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM public.claims WHERE case_id = %s",
                (case_id,),
            )
            if cur.fetchone() is None:
                cur.execute(
                    """
                    INSERT INTO public.claims (
                        case_id,
                        policy_number,
                        claimant_name,
                        claim_type,
                        claim_amount,
                        description,
                        status
                    ) VALUES (%s, %s, %s, %s, %s, %s, 'submitted')
                    """,
                    (case_id, "POL-1001", "Test Customer", "Medical", 30000.0, "Mismatch validation"),
                )
            cur.execute(
                """
                INSERT INTO public.documents (
                    document_id, case_id, file_name, document_type, extracted_text, confidence, injection_detected
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (document_id) DO NOTHING
                """,
                (
                    "DOC-MISMATCH-001",
                    case_id,
                    "hospital_bill.pdf",
                    "medical_bill",
                    "Hospital bill\nDate: 5/6/2026\nAmount: 200\nClaimant: Alex",
                    0.65,
                    False,
                ),
            )
            conn.commit()

    result = workflow.mcp_validation_node({"case_id": case_id, "claim_data": {"policy_number": "POL-1001", "claim_type": "Medical", "claim_amount": 30000.0}})

    assert result["document_validation"]["continue_allowed"] is False
    assert "amount_mismatch" in result["document_validation"]["risks"]
    assert "claimant_name_mismatch" in result["document_validation"]["risks"]


def test_missing_document_routes_to_await_documents(monkeypatch):
    monkeypatch.setattr(
        workflow,
        "_request_missing_documents",
        lambda case_id, missing: {"status": "awaiting_documents"},
    )

    state = {
        "case_id": "CASE-101",
        "current_stage": "documents_incomplete",
        "document_complete": False,
        "missing_documents": ["supporting_document"],
        "document_validation": {"continue_allowed": True},
        "errors": [],
    }

    result = workflow.supervisor_node(state)

    assert isinstance(result, Command)
    assert result.goto == "await_documents"
    assert "awaiting_documents" in result.update["status"]


def test_missing_documents_do_not_override_risk_manual_review():
    state = {
        "case_id": "CASE-101A",
        "current_stage": "documents_complete",
        "document_complete": True,
        "missing_documents": ["supporting_document"],
        "document_validation": {"continue_allowed": True, "missing_documents": ["supporting_document"]},
        "risks": ["low_confidence"],
        "errors": [],
    }

    result = workflow.supervisor_node(state)

    assert isinstance(result, Command)
    assert result.goto == "manual_review"
    assert "manual_review" in result.update["status"]


def test_low_confidence_document_routes_to_manual_review():
    state = {
        "case_id": "CASE-102",
        "current_stage": "documents_complete",
        "document_complete": True,
        "missing_documents": [],
        "document_validation": {"continue_allowed": True},
        "risks": ["low_confidence"],
        "errors": [],
    }

    result = workflow.supervisor_node(state)

    assert isinstance(result, Command)
    assert result.goto == "manual_review"
    assert "manual_review" in result.update["status"]


def test_prompt_injection_routes_to_manual_review():
    state = {
        "case_id": "CASE-103",
        "current_stage": "documents_complete",
        "document_complete": True,
        "missing_documents": [],
        "document_validation": {"continue_allowed": True},
        "risks": ["prompt_injection_detected"],
        "errors": [],
    }

    result = workflow.supervisor_node(state)

    assert isinstance(result, Command)
    assert result.goto == "manual_review"


def test_amount_mismatch_routes_to_manual_review():
    state = {
        "case_id": "CASE-104",
        "current_stage": "documents_complete",
        "document_complete": True,
        "missing_documents": [],
        "document_validation": {"continue_allowed": True},
        "risks": ["amount_mismatch"],
        "errors": [],
    }

    result = workflow.supervisor_node(state)

    assert isinstance(result, Command)
    assert result.goto == "manual_review"


def test_invalid_transition_is_blocked():
    state = {
        "case_id": "CASE-105",
        "current_stage": "finalized",
        "document_complete": True,
        "missing_documents": [],
        "document_validation": {"continue_allowed": True},
        "risks": [],
        "errors": [],
    }

    result = workflow.supervisor_node(state)

    assert isinstance(result, Command)
    assert result.goto == "manual_review"
    assert any("Invalid transition" in str(error) for error in result.update["errors"])


def test_manual_review_node_persists_manual_review_status_for_ui_queue():
    case_id = "CASE-MANUAL-QUEUE"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM public.claims WHERE case_id = %s",
                (case_id,),
            )
            if cur.fetchone() is None:
                cur.execute(
                    """
                    INSERT INTO public.claims (
                        case_id,
                        policy_number,
                        claimant_name,
                        claim_type,
                        claim_amount,
                        description,
                        status,
                        summary
                    ) VALUES (%s, %s, %s, %s, %s, %s, 'submitted', 'queued')
                    """,
                    (case_id, "POL-1001", "Queue Tester", "Medical", 15000.0, "Manual review queue check"),
                )
            conn.commit()

    original_interrupt = workflow.interrupt
    workflow.interrupt = lambda payload: {"action": "hold_case", "reviewer": "Ops Reviewer", "rationale": "Hold until evidence is clarified."}
    try:
        result = workflow.manual_review_node({"case_id": case_id, "risks": ["low_confidence"], "current_stage": "documents_complete"})
    finally:
        workflow.interrupt = original_interrupt

    assert result["status"] == "manual_review_held"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status FROM public.claims WHERE case_id = %s",
                (case_id,),
            )
            row = cur.fetchone()
    assert row["status"] == "manual_review_held"


def test_manual_review_resume_keeps_fields_separate(monkeypatch):
    state = {
        "case_id": "CASE-106A",
        "summary_result": "Summary ready",
        "routing_result": "Route to adjuster",
        "manual_review_reason": "low_confidence",
        "risks": ["low_confidence"],
    }

    monkeypatch.setattr(
        workflow,
        "interrupt",
        lambda payload: {
            "action": "continue_processing",
            "reviewer": "Ops Reviewer",
            "rationale": "The low-confidence document was reprocessed and cleared.",
            "resolved_risks": ["low_confidence"],
        },
    )

    result = workflow.manual_review_node(state)

    assert isinstance(result, Command)
    assert result.goto == "documents"
    assert result.update["manual_review_action"] == "continue_processing"
    assert result.update["manual_review_reviewer"] == "Ops Reviewer"
    assert result.update["manual_review_rationale"] == "The low-confidence document was reprocessed and cleared."
    assert "human_decision" not in result.update
    assert "human_reviewer" not in result.update
    assert "human_rationale" not in result.update


def test_manual_review_reprocess_keeps_low_confidence_blocking(monkeypatch):
    state = {
        "case_id": "CASE-106B",
        "summary_result": "Summary ready",
        "routing_result": "Route to adjuster",
        "manual_review_reason": "low_confidence",
        "risks": ["low_confidence"],
        "document_complete": True,
    }

    monkeypatch.setattr(
        workflow,
        "interrupt",
        lambda payload: {
            "action": "reprocess_documents",
            "reviewer": "Ops Reviewer",
            "rationale": "Document confidence is still 0.30 and needs revalidation.",
        },
    )

    result = workflow.manual_review_node(state)
    assert isinstance(result, Command)
    assert result.goto == "documents"
    assert result.update["status"] == "documents_revalidated"
    assert result.update["current_stage"] == "documents_revalidated"

    resumed = {
        **result.update,
        "case_id": "CASE-106B",
        "current_stage": "documents_revalidated",
        "status": "documents_revalidated",
        "risks": ["low_confidence"],
        "document_complete": False,
        "document_validation": {"continue_allowed": False},
    }
    routed = workflow.supervisor_node(resumed)
    assert routed.goto == "manual_review"
    assert routed.update["status"] == "manual_review"


def test_manual_review_continue_processing_is_blocked_while_low_confidence_remains(monkeypatch):
    state = {
        "case_id": "CASE-106C",
        "summary_result": "Summary ready",
        "routing_result": "Route to adjuster",
        "manual_review_reason": "low_confidence",
        "risks": ["low_confidence"],
        "document_complete": True,
        "security_flags": [],
    }

    monkeypatch.setattr(
        workflow,
        "interrupt",
        lambda payload: {
            "action": "continue_processing",
            "reviewer": "Ops Reviewer",
            "rationale": "Resume without resolving the low-confidence evidence.",
            "resolved_risks": [],
        },
    )

    result = workflow.manual_review_node(state)
    assert isinstance(result, Command)
    assert result.goto == "manual_review"
    assert result.update["status"] == "manual_review"
    assert "low_confidence" in result.update["risks"]


def test_human_review_resume_sets_decision():
    monkeypatch = None
    state = {
        "case_id": "CASE-106",
        "summary_result": "Summary ready",
        "routing_result": "Route to adjuster",
    }

    original_interrupt = workflow.interrupt
    workflow.interrupt = lambda payload: {
        "decision": "approved",
        "rationale": "Reviewed by authorized reviewer.",
        "reviewer": "Approver A",
    }
    try:
        result = workflow.human_review_node(state)
    finally:
        workflow.interrupt = original_interrupt

    assert result["human_decision"] == "approved"
    assert result["current_stage"] == "human_review_complete"


def test_human_review_request_more_information_is_non_final():
    state = {
        "case_id": "CASE-106B",
        "summary_result": "Summary ready",
        "routing_result": "Route to adjuster",
    }

    original_interrupt = workflow.interrupt
    workflow.interrupt = lambda payload: {
        "decision": "request_more_information",
        "rationale": "Need an itemized bill and proof of treatment.",
        "reviewer": "Approver A",
        "missing_documents": ["itemized_bill", "treatment_proof"],
    }
    try:
        result = workflow.human_review_node(state)
    finally:
        workflow.interrupt = original_interrupt

    assert isinstance(result, Command)
    assert result.goto == "await_documents"
    assert result.update["human_decision"] == "request_more_information"
    assert result.update["status"] == "awaiting_documents"
    assert result.update["current_stage"] == "awaiting_documents"
    assert result.update["missing_documents"] == ["itemized_bill", "treatment_proof"]


def test_record_audit_redacts_secrets_and_deduplicates():
    case_id = "CASE-AUDIT-REDACT"
    first = record_audit(
        case_id,
        "system",
        "workflow_started",
        {
            "api_key": "super-secret-key",
            "password": "secret-pass",
            "document_text": "Claimant Name: Test Customer\nAmount: $25,000",
            "stage": "submitted",
        },
        stage="submitted",
    )
    second = record_audit(
        case_id,
        "system",
        "workflow_started",
        {
            "api_key": "super-secret-key",
            "password": "secret-pass",
            "document_text": "Claimant Name: Test Customer\nAmount: $25,000",
            "stage": "submitted",
        },
        stage="submitted",
    )

    assert first["duplicate"] is False
    assert second["duplicate"] is True

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT details
                FROM public.claim_audit
                WHERE case_id = %s
                  AND action = 'workflow_started'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (case_id,),
            )
            row = cur.fetchone()

    details = row["details"] if isinstance(row, dict) else row[0] if row else {}
    redacted_json = str(details)
    assert "super-secret-key" not in redacted_json
    assert "secret-pass" not in redacted_json
    assert "Claimant Name" not in redacted_json
    assert "_audit_key" in details


def test_missing_document_resume_revalidates_documents(monkeypatch):
    original_interrupt = workflow.interrupt
    workflow.interrupt = lambda payload: {"document_text": "Claimant Name: Jane Doe\nAmount: $25,000"}
    try:
        state = {
            "case_id": "CASE-107",
            "claim_data": {"document_text": ""},
            "missing_documents": ["supporting_document"],
            "current_stage": "awaiting_documents",
        }
        result = workflow.await_documents_node(state)
    finally:
        workflow.interrupt = original_interrupt

    assert isinstance(result, Command)
    assert result.goto == "documents"
    assert result.update["missing_documents"] == []
    assert result.update["current_stage"] == "documents_revalidated"
    assert result.update["status"] == "documents_revalidated"
