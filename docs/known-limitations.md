# Known limitations

## Prototype limitations

- This is a local demo and evaluation implementation, not a production claims-payment or compliance system.
- The workflow relies on local Postgres and Ollama setup, not a managed production environment.
- The project is intended for evaluation and demonstration, not high-volume processing.

## Unsupported functionality

- No production identity or access-management integration is implemented.
- No external payment, adjudication, or insurer API integration is included.
- No KYC, fraud, or regulatory compliance engine beyond the demo guard rails is part of the active implementation.
- No Kubernetes, Keycloak, Phoenix, or MLflow components are implemented in this repository.

## Production recommendations

- Use a managed Postgres cluster with explicit backups and retention policies.
- Replace the demo approver model with a real RBAC-backed human review process.
- Harden OCR and document pipelines with production scanning controls and secure storage.
- Add explicit retention, secret rotation, and monitoring for all operational data.
