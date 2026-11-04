# Intelligent Claims Processing & Case Management Agent

This project delivers a LangGraph-driven claims workflow with MCP-backed validation, human review, audit traceability, and a Streamlit operator panel. It is optimized for a claims-processing demo environment and a portable local deployment via Docker Compose.

## Architecture

```mermaid
flowchart LR
    UI[Streamlit UI] --> WF[LangGraph workflow]
    WF --> INT[Ingestion / Intake]
    WF --> DOC[Document validation]
    WF --> SUM[Summary agent]
    WF --> ROUTE[Routing agent]
    WF --> SLA[SLA tracker]
    WF --> HR[Human review]
    WF --> AUDIT[Audit ledger]
    DOC --> MCP[Workflow MCP / Case MCP]
    HR --> MAIL[Mailpit notification]
    DB[(PostgreSQL)] --> AUDIT
    DB --> WF
```

## Core components

- LangGraph supervisor and guard logic in `graph/workflow_v2.py`
- Type-safe processed state in `graph/state.py`
- MCP servers under `mcp_servers/`
- Document extraction and validation in `services/document_processor.py`
- Streamlit demo UI in `app/streamlit_app.py`
- Audit logging in `services/audit.py`
- Mailpit-based demo notification support in `services/notifications.py`

## Local setup

1. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   . .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Configure environment variables in `.env`:
   ```env
   DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres
   MAILPIT_HOST=localhost
   MAILPIT_SMTP_PORT=1025
   MAILPIT_HTTP_PORT=8025
   ```
3. Start PostgreSQL and Mailpit:
   ```bash
   docker compose up -d
   ```
   This launches the app, Postgres, and Mailpit together for the demo environment.
4. Run the app locally:
   ```bash
   streamlit run app/streamlit_app.py
   ```

5. Or use the one-command demo launcher:
   ```bash
   ./start_demo.sh
   ```
   This starts PostgreSQL and Mailpit, then launches the Streamlit UI for the claims demo.

## Demo flow

- Submit a claim through the Streamlit form.
- The workflow validates documents and policy inputs.
- Missing documents trigger the request workflow.
- Human reviews are gated by approver-limit validation.
- All decisions are written to the audit log.

## Validation

Run the targeted supervisor and scenario suite:

```bash
./.venv/bin/python -m pytest tests/test_v2_supervisor.py tests/test_scenario_suite.py -q
```

Run the evaluation gate for the core routing scenarios:

```bash
./.venv/bin/python evaluation/scenario_eval.py
```

## Related components

- `graph/workflow_postgres.py` is the stable fallback workflow.
- `tests/test_v2_supervisor.py` covers the supervisor guard routing.
- `tests/test_scenario_suite.py` covers the demo operational scenarios.
