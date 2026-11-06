# Security and privacy

## Secret handling

- Environment variables are kept in `.env` for local runtime use only.
- `.env.example` contains placeholders only.
- The repository does not include committed production credentials, private keys, bearer tokens, or API secrets.
- Packaging excludes `.env`, secrets, and runtime artifacts.

## Prompt-injection behavior

The document processor and workflow use injection guards to treat extracted document text as untrusted. If a document contains prompt-injection patterns or suspicious instructions, the workflow records the risk and stops automatic progression. This prevents the automation from acting on untrusted embedded instructions.

## PII safety

The project includes redaction and minimization safeguards around PII. Audit records avoid exposing raw document content and review the sensitive payload only as summarized metadata. Synthetic test data is used wherever possible.

## MCP least privilege

Each MCP server is scoped to the operational actions it needs: case retrieval, policy lookup, document processing, workflow scheduling, and notification signaling. No server is configured to directly settle the claim or finalize payment decisions.

## Authorization

Human approval is constrained by approver-role checks and approval limits in the workflow and `workflow_mcp` server. Unsafe or unqualified approvers are blocked from final approval actions.

## Audit safety

The repository writes append-only workflow audit entries through `services/audit.py` so operational actions are traceable without exposing secret material or raw document bodies. The audit trail captures case ID, stage, outcome, and selected control metadata, not the full sensitive document payload.
