from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import graph.workflow_v2 as workflow


SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "clean_claim_routes_to_summary",
        "state": {
            "case_id": "CASE-200",
            "current_stage": "documents_complete",
            "document_complete": True,
            "missing_documents": [],
            "document_validation": {"continue_allowed": True},
            "risks": [],
            "errors": [],
        },
        "expected": "summary",
    },
    {
        "name": "missing_documents_routes_to_await_documents",
        "state": {
            "case_id": "CASE-201",
            "current_stage": "documents_incomplete",
            "document_complete": False,
            "missing_documents": ["supporting_document"],
            "document_validation": {"continue_allowed": True},
            "errors": [],
        },
        "expected": "await_documents",
    },
    {
        "name": "low_confidence_routes_to_manual_review",
        "state": {
            "case_id": "CASE-202",
            "current_stage": "documents_complete",
            "document_complete": True,
            "missing_documents": [],
            "document_validation": {"continue_allowed": True},
            "risks": ["low_confidence"],
            "errors": [],
        },
        "expected": "manual_review",
    },
    {
        "name": "prompt_injection_routes_to_manual_review",
        "state": {
            "case_id": "CASE-203",
            "current_stage": "documents_complete",
            "document_complete": True,
            "missing_documents": [],
            "document_validation": {"continue_allowed": True},
            "risks": ["prompt_injection_detected"],
            "errors": [],
        },
        "expected": "manual_review",
    },
    {
        "name": "invalid_transition_is_blocked",
        "state": {
            "case_id": "CASE-204",
            "current_stage": "finalized",
            "document_complete": True,
            "missing_documents": [],
            "document_validation": {"continue_allowed": True},
            "risks": [],
            "errors": [],
        },
        "expected": "manual_review",
    },
    {
        "name": "sla_completion_routes_to_human_review",
        "state": {
            "case_id": "CASE-205",
            "current_stage": "sla_complete",
            "document_complete": True,
            "missing_documents": [],
            "document_validation": {"continue_allowed": True},
            "risks": [],
            "errors": [],
        },
        "expected": "human_review",
    },
    {
        "name": "human_review_completion_routes_to_finalize",
        "state": {
            "case_id": "CASE-206",
            "current_stage": "human_review_complete",
            "document_complete": True,
            "missing_documents": [],
            "document_validation": {"continue_allowed": True},
            "risks": [],
            "errors": [],
        },
        "expected": "finalize",
    },
    {
        "name": "submitted_claim_requires_intake",
        "state": {
            "case_id": "CASE-207",
            "current_stage": "submitted",
            "document_complete": True,
            "missing_documents": [],
            "document_validation": {"continue_allowed": True},
            "risks": [],
            "errors": [],
        },
        "expected": "intake",
    },
]


def evaluate_scenarios() -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    passed = 0

    for scenario in SCENARIOS:
        result = workflow.supervisor_node(scenario["state"])
        actual = getattr(result, "goto", None)
        status = actual == scenario["expected"]
        if status:
            passed += 1

        results.append({
            "name": scenario["name"],
            "expected": scenario["expected"],
            "actual": actual,
            "passed": status,
        })

    total = len(results)
    pass_rate = round((passed / total) * 100, 2) if total else 0.0
    threshold = 80.0

    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": pass_rate,
        "threshold": threshold,
        "passed_gate": pass_rate >= threshold,
        "results": results,
    }


def main() -> None:
    summary = evaluate_scenarios()
    print(json.dumps(summary, indent=2))
    if not summary["passed_gate"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
