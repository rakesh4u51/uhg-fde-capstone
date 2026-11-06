import json

from evaluation.scenario_eval import build_default_scenarios, evaluate_workflow_gate


def test_default_scenarios_include_real_workflow_paths():
    scenarios = build_default_scenarios()
    assert scenarios
    names = {scenario["scenario_id"] for scenario in scenarios}
    assert "CLEAN-CLAIM" in names
    assert "MISSING-DOC" in names
    assert "PROMPT-INJECTION" in names


def test_evaluation_gate_marks_mandatory_failures():
    report = evaluate_workflow_gate()
    assert "release_ready" in report
    assert "mandatory_failures" in report
    assert "warnings" in report
    assert isinstance(report["mandatory_failures"], list)
    assert isinstance(report["warnings"], list)
    assert "release_ready" in report


def test_evaluation_report_excludes_sensitive_fields():
    report = evaluate_workflow_gate()
    rendered = json.dumps(report)
    assert "DATABASE_URL" not in rendered
    assert "OPENROUTER_API_KEY" not in rendered
    assert "api_key" not in rendered.lower()


def test_evaluation_gate_requires_all_mandatory_categories():
    report = evaluate_workflow_gate()
    categories = {scenario["category"] for scenario in report["scenarios"]}
    assert {"functional", "workflow", "security", "human_control", "authorization", "persistence"}.issubset(categories)
    assert "category_coverage" in report
    assert report["coverage_status"] == "complete"
