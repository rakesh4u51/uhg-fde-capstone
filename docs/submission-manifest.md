# Submission manifest

## Included source and documentation

The following actual repository content is included in the submission package:

- README.md
- SUBMISSION_CHECKLIST.md
- .env.example
- .gitignore
- requirements.txt
- Dockerfile
- docker-compose.yml
- start_demo.sh
- app/
- graph/
- agents/
- services/
- mcp_servers/
- database/
- scripts/
- tests/
- evaluation/
- docs/
- sample_data/
- security/
- models/
- source/
- medical_bill.md (only if included intentionally as a synthetic example; excluded from the packaging script by default)

## Excluded from the final package

- .env
- .env.* except `.env.example`
- .streamlit/secrets.toml
- .venv/
- venv/
- env/
- __pycache__/
- *.pyc
- .pytest_cache/
- uploads/
- runtime_data/
- checkpoints/
- logs/
- pgdata/
- postgres-data/
- model files
- local IDE metadata
- git metadata
- chat and session exports
