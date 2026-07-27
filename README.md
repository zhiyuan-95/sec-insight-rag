# SEC Insight RAG

Local Python backend for traceable financial research from SEC filings, XBRL
facts, deterministic calculations, filing retrieval, and evidence-grounded LLM
analysis.

## Local Setup

```powershell
uv sync
Copy-Item config.env.example config.env
uv run python -m pytest -q
uv run uvicorn src.api.main:app --reload
```

Configure `SEC_USER_AGENT` before live SEC requests. Configure provider keys
only for workflows that call those providers. Never commit `config.env`.

## Current Direction

The approved structured-data path processes all selected annual Inline XBRL
`10-K`/`10-K/A` filings through Arelle-backed evidence extraction and
source-aware metric mapping. Filing retrieval, indicators, analysis, RAG, and
API workflows remain separate capabilities.

Current runtime behavior may implement only part of an approved milestone.
Use the milestone index for status and `docs/structure.md` for implemented
truth.

## Documentation Map

- [Project proposal](proposal.md): overall direction, architecture, and roadmap
- [Milestone index](docs/milestones/README.md): status, dependencies, and plans
- [Domain glossary](CONTEXT.md): canonical project terminology
- [Current structure](docs/structure.md): implemented modules and storage
- [Mapping policy](docs/policies/mapping.md): durable mapping governance
- [Experiment runbook](docs/experiments.md): shared inspection conventions
- [Agent contract](agents.md): repository rules for coding agents
