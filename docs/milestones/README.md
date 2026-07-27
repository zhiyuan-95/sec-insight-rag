# Milestone Index

This index is the navigation and status source for project milestones.
`proposal.md` owns the overall roadmap. Each linked milestone file owns the
high-fidelity design for that subproject. `docs/structure.md` remains the source
of truth for currently implemented runtime behavior.

## Status Vocabulary

- `draft`: design decisions are still being resolved.
- `approved`: the design is accepted and ready for implementation.
- `active`: implementation or acceptance work is underway.
- `completed`: implementation and acceptance evidence are complete.
- `superseded`: a later approved milestone replaced the plan.

## Roadmap

| Milestone | Capability | Status | Depends on | Plan | Remaining work or evidence |
| --- | --- | --- | --- | --- | --- |
| MS1 | Foundation and configuration | completed | — | [MS1](MS1-foundation.md) | Preserve scaffold and health/configuration checks |
| MS2 | Annual Inline XBRL ingestion and evidence | active | MS1 | [MS2](MS2-annual-xbrl-ingestion.md) | Wire the implemented seams into the annual company workflow and run the complete-history proof |
| MS3 | Base metric mapping and recovery | active | MS2 | [MS3](MS3-base-metric-mapping.md) | Period application, recovered-metric persistence, atomic publication, and the complete proof report |
| MS4 | Derived financial indicators | active | MS3 | [MS4](MS4-indicators.md) | Validate the existing plan's complete annual and quarterly report contract |
| MS5 | Deterministic financial analysis | draft | MS4 | — | Design through a future grilling session |
| MS6 | Filing-text ingestion and retrieval | active | MS2 | [MS6](MS6-filing-retrieval.md) | Re-evaluate completion evidence after renumbering |
| MS7 | Evidence-grounded LLM analysis and RAG | draft | MS3, MS5, MS6 | — | Design through a future grilling session |
| MS8 | API, workflows, and end-to-end evaluation | draft | MS3–MS7 | — | Design through a future grilling session |

## Lifecycle

A milestone plan is created only after its design has been resolved. An
accepted plan remains tracked after completion so agents can trace the original
contract and evidence. Small adjustments reopen the same plan as `active`;
material changes to its purpose or architecture require a new milestone that
marks the earlier plan `superseded`.

Generated reports and databases remain untracked. A completed plan records the
commands, artifact locations, commits, and limitations needed to reproduce its
acceptance evidence.
