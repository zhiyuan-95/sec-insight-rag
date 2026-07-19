# Arelle Integration Assessment

Assessment date: 2026-07-15

## Recommendation

**Use Arelle as a complement to SEC Company Facts, not as its replacement.**

For the repository's literal Milestone 2 contract, Arelle is not needed to
resolve tickers, retrieve submissions, select/download 10-K and 10-Q filings,
normalize standard entity-wide `us-gaap` facts, or store `NormalizedFact` rows.
Those responsibilities are already implemented and are exactly what the MS2
experiment inspects.

Arelle is valuable for the later raw-fact-to-system-metric workflow now scoped
under MS200: it can load a filing's Inline XBRL instance and DTS,
extract issuer-extension and dimensional facts, inspect contexts/units, run
validation, and traverse presentation, calculation, and dimensional
relationships. The SEC confirms why this is complementary: Company Facts only
aggregates non-custom-taxonomy facts that apply to the entire filing entity, so
it excludes custom concepts and many dimensional facts.
([SEC EDGAR API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces))

Use those additional structures as **report-only evidence** for unresolved
metric review. Arelle must not automatically approve a concept mapping,
manufacture a reported fact, or persist a recovered metric.

## Current Repository State

The repository already uses Arelle:

- `pyproject.toml` declares `arelle-release>=2.41,<3.0`; `uv.lock` currently
  resolves 2.41.5 on the local Windows/Python 3.10.11 runtime.
- `src/ingestion/inline_xbrl.py` uses `Cntlr.Cntlr`, sets the SEC user agent,
  loads a filing URL, and closes the model/controller.
- `src/processing/inline_xbrl.py` walks `model_xbrl.facts` and retains custom or
  dimensional facts in the existing `NormalizedFact` contract.
- `src/ingestion/company.py` first stores broad Company Facts, then invokes
  Arelle only when deterministic target coverage remains incomplete.

That broad-first, filing-level-second architecture is sound. It keeps Company
Facts as the efficient historical archive and pays DTS-loading cost only when
filing-specific evidence could help.

The gaps are testability and integration depth:

- The MS2 experiment still uses only Company Facts. Its synthetic filing HTML
  is not a real Inline XBRL instance with extension schemas/linkbases.
- No focused tests exercise `src/ingestion/inline_xbrl.py` or
  `src/processing/inline_xbrl.py`.
- The adapter counts `model_xbrl.errors` after `modelManager.load()` but does
  not run an explicit documented validation/calculation session.
- It loads the SEC document URL, so Arelle can refetch the filing and taxonomy
  dependencies outside the project's `SecClient` retry/throttle path.
- Inline normalization derives `taxonomy` from the filing's QName prefix while
  base metric lookup keys on `(taxonomy, concept)`. Before approving issuer
  extension mappings, verify them against the stored namespace URI so a prefix
  change cannot redirect or break an approved mapping.

A focused local run of the existing MS2 and Company Facts tests completed with
`22 passed`; that verifies the current path, not Arelle behavior.

## Capability-to-Project Fit

Arelle officially supports XBRL 2.1, Dimensions, Formula, Taxonomy Packages,
Inline XBRL 1.1, GUI/CLI/Python/Web interfaces, plugins, and SEC EFM rules.
([Arelle README](https://github.com/Arelle/Arelle#features))

| Project need | Fit | Integration decision |
| --- | --- | --- |
| Ticker/CIK, submissions, refresh, filing selection/download | Non-fit | Keep project SEC modules and repositories. |
| Standard entity-wide history | Possible but unnecessary replacement | Keep Company Facts as the primary source. |
| Inline XBRL transforms | Strong complement | Let Arelle parse filing values instead of adding custom transform logic. |
| Issuer extensions and dimensional facts | Strong complement | Normalize into existing raw facts with accession/source lineage. |
| Concept labels, documentation, type, balance | Useful evidence | Show in mapping review; never treat as mapping approval. |
| Contexts and units | Strong complement | Preserve exact period/entity/dimensions/unit measures. |
| Presentation relationships | Useful evidence | Use roles and parent-child neighbors to identify statement placement. |
| Calculation relationships | Useful but limited evidence | Use children/weights as candidate formula evidence only when context/unit rules bind. |
| Definition/dimensional relationships | Useful evidence | Use axes/domains/members/defaults to interpret disaggregated facts. |
| XBRL/calculation/EFM diagnostics | Useful quality evidence | Capture diagnostic codes and severity without deleting source facts. |
| Internal metric vocabulary, approval policy, SQLite | Non-fit | Keep mapping catalogs, policies, and repositories authoritative. |

### Facts and relationships

The supported Python API returns loaded `ModelXbrl` objects. A model exposes
facts by QName/local name/period/dimension, contexts and units in use,
dimensions, errors, and `relationshipSet(arcrole, linkrole, ...)`.
([`ModelXbrl` API](https://arelle.readthedocs.io/en/2.41.2/apidocs/arelle/arelle.ModelXbrl.html))
Facts expose concept, context, unit, value, decimals, precision, and Inline XBRL
metadata; units expose numerator/denominator measures.
([fact/context/unit API](https://arelle.readthedocs.io/en/latest/apidocs/arelle/arelle.ModelInstanceObject.html))
Relationship sets support link roles, roots, and from/to traversal.
([`ModelRelationshipSet` API](https://arelle.readthedocs.io/en/2.37.73/apidocs/arelle/arelle.ModelRelationshipSet.html))

Arelle defines arcroles for presentation `parent-child`, calculation
`summation-item`, and dimensional definition networks such as
`hypercube-dimension`, `dimension-domain`, and `domain-member`.
([`XbrlConst` API](https://arelle.readthedocs.io/en/2.37.50/apidocs/arelle/arelle.XbrlConst.html))
These can improve MS200 evidence, but calculation relationships are not a
general formula engine. XBRL 2.1 calculations bind only under context, unit,
duplicate, and weighted-sum rules, and their expressive scope is limited.
([XBRL 2.1 calculation rules](https://www.xbrl.org/Specification/xbrl-recommendation-2003-12-31.pdf),
[XBRL International validation overview](https://specifications.xbrl.org/validation.html))

Therefore, a calculation tree can support a formula recommendation; it cannot
prove that an absent target fact should be synthesized or that two concepts are
equivalent.

## Validation And Packaging Boundaries

Arelle's CLI/Python runtime can load local or remote instances, schemas,
linkbases, and Inline XBRL. It supports core XBRL validation, explicit
calculation modes, taxonomy packages, plugins, offline/cache controls, and
profiling.
([command-line documentation](https://arelle.readthedocs.io/en/2.40.1/command_line.html))

The project should distinguish four categories instead of calling every model
error a validation message:

1. document/DTS load diagnostics;
2. core XBRL validation;
3. calculation consistency validation; and
4. SEC EDGAR Filer Manual validation.

The current base PyPI dependency is not comprehensive EFM validation. Arelle's
official installation guide says prepackaged distributions include EDGAR/XULE,
but source and PyPI installs do not; `[EFM]` installs dependencies, not the
EDGAR plugin itself.
([installation documentation](https://arelle.readthedocs.io/en/latest/install.html))
The SEC-maintained EDGAR plugin is separate, integrates with EFM validation,
and has its own version/dependency coordination.
([EDGAR plugin documentation](https://arelle.readthedocs.io/en/2.39.3/plugins/popular/edgar.html),
[official EDGAR plugin repository](https://github.com/Arelle/EDGAR))

Core loading, extraction, relationship traversal, and validation are enough
for the first proof. Add the SEC plugin only if its diagnostics materially
improve ingestion or mapping decisions.

## Interface, Concurrency, Performance, And Security

The official documentation calls `arelle.api.Session` the supported embedding
API. It provides `RuntimeOptions`, structured logs, model retrieval, packages,
plugins, validation, and lifecycle management.
([Python API](https://arelle.readthedocs.io/en/latest/python_api/python_api.html))
The current low-level `Cntlr.Cntlr` use should eventually sit behind a
`Session`-based adapter without changing downstream project interfaces.

Concurrency is the main operational risk. Arelle warns that package/plugin
managers use shared global state and are not thread-safe: only one Session may
run at a time per process, and parallel work requires a process pool rather
than threads.
([Python API concurrency warning](https://arelle.readthedocs.io/en/latest/python_api/python_api.html))
The current code also temporarily disables the process-global `arelle` logger.
Start with serialized execution; use isolated processes only after measurement.

Arelle publishes cache and profiling controls but no latency budget for this
workload. Measure cold/warm filing load time, taxonomy downloads/cache hits,
fact counts, diagnostics, and duplicate requests. Keep Company Facts ingestion
successful if Arelle fails.

Do not add the built-in web server. It has no authentication and is intended
only for trusted callers, adding a service/security surface outside current
scope.
([CLI web-server warning](https://arelle.readthedocs.io/en/2.40.1/command_line.html),
[web-server security guidance](https://arelle.readthedocs.io/en/2.41.3/webserver_security.html))

## Platform, Release, And License

Arelle declares Python `>=3.10`, Python 3.10-3.14 classifiers, and
OS-independent packaging, matching this repository.
([Arelle `pyproject.toml`](https://github.com/Arelle/Arelle/blob/master/pyproject.toml))
The project is active: 2.42.1 was released on 2026-07-13, while this repository
locks 2.41.5.
([Arelle releases](https://github.com/Arelle/Arelle/releases))
Because the dependency range permits minor upgrades, adapter regression tests
should gate any lock refresh.

Arelle core is Apache-2.0; included libraries and separate plugins can have
their own notices.
([Arelle license](https://github.com/Arelle/Arelle/blob/master/LICENSE.md))
Review each added plugin separately and preserve applicable notices.

## Staged Proof Of Concept

Do not change the database schema, public APIs, mapping approvals, or MS2
report contract during this proof.

1. **Stabilize the adapter.** Keep `get_inline_xbrl_facts()` as the boundary,
   implement it with one serialized `Session` per process, capture structured
   diagnostics, and return only project-owned result objects.
2. **Use genuine saved filings.** Add a dedicated immutable proof fixture with
   one real 10-K and one real 10-Q filing package, including extension XSD and
   linkbases. Keep the existing MS2 fixtures unchanged.
3. **Reconcile sources.** Compare overlapping accession-scoped Company Facts
   and Arelle facts by concept, period, unit, value, and accession. Explain
   mismatches; confirm custom/dimensional additions do not overwrite the
   Company Facts archive. Verify issuer-extension mapping identity using the
   namespace URI rather than trusting a filing-local QName prefix alone.
4. **Measure cost.** Record exact Arelle version, namespaces, facts seen/kept,
   diagnostics by category, taxonomy downloads, cache state, and cold/warm
   duration.
5. **Add MS200 report-only evidence.** For each unresolved internal metric,
   show target-in-DTS status, target facts, concept metadata, presentation
   neighbors, calculation children/weights, dimensions, and relevant
   diagnostics. Do not populate metrics or approve mappings.
6. **Evaluate EFM separately.** First measure core XBRL/calculation validation;
   add a pinned compatible Arelle/EDGAR/XULE stack only if the extra findings
   change decisions.

Adopt the expanded integration only if both filing forms load reproducibly,
overlapping facts reconcile, extensions/dimensions materially improve evidence,
at least one real unresolved-metric review improves without bypassing
governance, failures preserve Company Facts results, execution is serialized or
process-isolated, and focused tests protect version upgrades.

Otherwise, retain the current narrow adaptive enrichment. The existing Company
Facts path already answers Milestone 2's central question; Arelle's material
value is deeper filing-specific evidence for the mapping milestone.
