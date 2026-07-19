"""Report-only deterministic mapping inference from detached Arelle evidence."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable, Mapping
from urllib.parse import urlparse

from src.processing.arelle_precedence import ArelleObservation, apply_arelle_accession_precedence
from src.processing.arelle_records import (
    ArelleFilingResult,
    ConceptEvidence,
    QNameKey,
    RelationshipEdge,
)
from src.processing.mapping_targets import CanonicalMetricTarget


INFERENCE_CONTRACT_VERSION = "arelle-evidence-inference-v1"
INFERENCE_THRESHOLD = "uncalibrated_shadow"
EVIDENCE_INDEPENDENCE = "not_assumed"
INFERENCE_OUTCOMES = {"unique_top_candidate", "needs_review", "no_candidate"}

_ROLE_KEYWORDS = {
    "balance_sheet": ("balance", "financialposition", "financial position"),
    "income_statement": ("income", "operations", "earnings", "profitloss"),
    "cash_flow_statement": ("cashflow", "cash flow"),
    "statement_of_equity": ("equity", "stockholder", "shareholder"),
}
_BLOCKING_DIAGNOSTIC_SEVERITIES = {"error", "fatal"}
_STANDARD_NAMESPACE_HOSTS = {
    "fasb.org": "us-gaap",
    "xbrl.sec.gov": "sec",
    "www.xbrl.org": "xbrl",
}


@dataclass(frozen=True)
class ArelleInferenceResult:
    """Complete, inspectable projection for one missing target metric."""

    target_metric: str
    target_statement: str
    outcome: str
    top_candidate_qname: str | None
    top_candidate_score: int
    runner_up_candidate_qname: str | None
    runner_up_score: int | None
    runner_up_citations: tuple[str, ...]
    strongest_competing_target: str | None
    strongest_competing_target_score: int | None
    strongest_competing_target_citations: tuple[str, ...]
    statement_role_score: int
    presentation_neighborhood_score: int
    relationship_network_score: int
    cross_form_recurrence_score: int
    governed_lexical_score: int
    metric_candidate_margin: int
    concept_target_margin: int
    accepted_observation_count: int
    rejected_observation_count: int
    accepted_accession_count: int
    rejected_accession_count: int
    observed_accessions: tuple[str, ...]
    hard_gates: tuple[tuple[str, str], ...]
    rejection_totals: tuple[tuple[str, int], ...]
    rejection_examples: tuple[tuple[str, tuple[str, ...]], ...]
    citations: tuple[str, ...]
    reason: str
    contract_version: str = INFERENCE_CONTRACT_VERSION
    threshold: str = INFERENCE_THRESHOLD
    evidence_independence: str = EVIDENCE_INDEPENDENCE

    def __post_init__(self) -> None:
        category_scores = (
            self.statement_role_score,
            self.presentation_neighborhood_score,
            self.relationship_network_score,
            self.cross_form_recurrence_score,
            self.governed_lexical_score,
        )
        if self.outcome not in INFERENCE_OUTCOMES:
            raise ValueError(f"Unknown inference outcome: {self.outcome}")
        if any(score < 0 or score > 2 for score in category_scores):
            raise ValueError("Inference category scores must be between 0 and 2")
        if sum(category_scores) != self.top_candidate_score:
            raise ValueError("Top-candidate score must equal the five category scores")
        if self.contract_version != INFERENCE_CONTRACT_VERSION:
            raise ValueError("Unsupported inference contract version")
        if self.threshold != INFERENCE_THRESHOLD:
            raise ValueError("Inference threshold must remain uncalibrated shadow evidence")
        if self.evidence_independence != EVIDENCE_INDEPENDENCE:
            raise ValueError("Evidence independence cannot be assumed")
        if self.metric_candidate_margin < 0:
            raise ValueError("Metric-candidate margin cannot be negative")
        if self.outcome == "no_candidate" and self.top_candidate_qname is not None:
            raise ValueError("no_candidate cannot name a top candidate")
        if self.outcome != "no_candidate" and not self.top_candidate_qname:
            raise ValueError("Candidate outcomes require a top candidate")
        if self.outcome == "unique_top_candidate" and (
            self.metric_candidate_margin <= 0 or self.concept_target_margin <= 0
        ):
            raise ValueError("Unique inference requires positive margins in both directions")
        if self.top_candidate_qname and not self.citations:
            raise ValueError("A named inference candidate requires evidence citations")


def infer_arelle_evidence_mappings(
    results: Iterable[ArelleFilingResult],
    *,
    missing_targets: Iterable[CanonicalMetricTarget],
    applicable_targets: Iterable[CanonicalMetricTarget],
    reconciliation_conflicts: Mapping[str, frozenset[tuple[str, str]]] | None = None,
) -> tuple[ArelleInferenceResult, ...]:
    """Rank missing-target candidates without activating or persisting mappings.

    Scores rank candidates only inside this proof session. They are not a
    confidence, probability, or production approval decision.
    """
    result_rows = tuple(results)
    missing_rows = tuple(missing_targets)
    target_rows = tuple(applicable_targets)
    conflict_keys = reconciliation_conflicts or {}
    precedence = apply_arelle_accession_precedence(result_rows)
    concept_evidence = {
        concept.concept_key: concept
        for result in result_rows
        for concept in result.concepts
    }
    relationships = tuple(
        relationship
        for result in result_rows
        for relationship in result.relationships
    )
    relationships_by_concept: dict[QNameKey, list[RelationshipEdge]] = defaultdict(list)
    for relationship in relationships:
        relationships_by_concept[relationship.from_concept].append(relationship)
        if relationship.to_concept != relationship.from_concept:
            relationships_by_concept[relationship.to_concept].append(relationship)
    diagnostics = {
        (result.accession_number, diagnostic.concept_key)
        for result in result_rows
        for diagnostic in result.diagnostics
        if diagnostic.severity in _BLOCKING_DIAGNOSTIC_SEVERITIES
        and diagnostic.concept_key is not None
    }

    grouped: dict[str, list[ArelleObservation]] = defaultdict(list)
    for observation in precedence.selected:
        grouped[_normalized_name(observation.fact.concept_key.local_name)].append(observation)

    candidates: dict[str, dict[str, object]] = {}
    global_rejections: Counter[str] = Counter()
    global_examples: dict[str, list[str]] = defaultdict(list)
    for normalized_local, observations in sorted(grouped.items()):
        qnames = tuple(sorted({item.fact.concept_key for item in observations}))
        families = {_namespace_family(qname.namespace_uri) for qname in qnames}
        display = _display_qname(qnames[0]) if qnames else normalized_local
        if len(families) > 1:
            _record_rejection(
                global_rejections,
                global_examples,
                "namespace_family_collision",
                f"{display}: {', '.join(sorted(families))}",
            )
            continue
        candidates[normalized_local] = {
            "qnames": qnames,
            "display": display,
            "observations": tuple(observations),
            "relationships": tuple(
                dict.fromkeys(
                    relationship
                    for qname in qnames
                    for relationship in relationships_by_concept.get(qname, ())
                )
            ),
        }

    pair_rows: dict[tuple[str, str, str], dict[str, object]] = {}
    for target in target_rows:
        for candidate_key, candidate in candidates.items():
            pair_rows[(target.metric_name, target.statement_type, candidate_key)] = _score_pair(
                target,
                candidate_key,
                candidate,
                concept_evidence=concept_evidence,
                diagnostics=diagnostics,
                reconciliation_conflicts=conflict_keys,
            )

    output: list[ArelleInferenceResult] = []
    for target in missing_rows:
        output.append(
            _project_target_result(
                target,
                target_rows,
                pair_rows,
                global_rejections,
                global_examples,
            )
        )
    return tuple(sorted(output, key=lambda item: (item.target_statement, item.target_metric)))


def _score_pair(
    target: CanonicalMetricTarget,
    candidate_key: str,
    candidate: Mapping[str, object],
    *,
    concept_evidence: Mapping[QNameKey, ConceptEvidence],
    diagnostics: set[tuple[str, QNameKey]],
    reconciliation_conflicts: Mapping[str, frozenset[tuple[str, str]]],
) -> dict[str, object]:
    observations = tuple(candidate["observations"])
    qnames = tuple(candidate["qnames"])
    accepted: list[ArelleObservation] = []
    rejected_accessions: set[str] = set()
    rejections: Counter[str] = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    expected_period = _expected_period_type(target.statement_type)
    for observation in observations:
        fact = observation.fact
        evidence = concept_evidence.get(fact.concept_key)
        reason: str | None = None
        if fact.context_key.dimensions:
            reason = "dimensional_observation"
        elif expected_period and fact.context_key.period_type != expected_period:
            reason = "period_type_incompatible"
        elif evidence is not None and not evidence.is_numeric:
            reason = "numeric_kind_incompatible"
        elif fact.unit_key is None:
            reason = "unit_incompatible"
        elif (observation.accession_number, fact.concept_key) in diagnostics:
            reason = "blocking_arelle_diagnostic"
        elif (
            _taxonomy_family(fact.concept_key.namespace_uri),
            fact.concept_key.local_name,
        ) in reconciliation_conflicts.get(observation.accession_number, frozenset()):
            reason = "unresolved_reconciliation_conflict"
        if reason is None:
            accepted.append(observation)
        else:
            rejected_accessions.add(observation.accession_number)
            _record_rejection(
                rejections,
                examples,
                reason,
                f"{observation.accession_number} {_display_qname(fact.concept_key)}",
            )

    if not accepted:
        return {
            "candidate_key": candidate_key,
            "display": candidate["display"],
            "scores": (0, 0, 0, 0, 0),
            "total": 0,
            "accepted": 0,
            "rejected": len(observations),
            "accessions": (),
            "rejected_accessions": tuple(sorted(rejected_accessions)),
            "all_accessions": tuple(
                sorted({item.accession_number for item in observations})
            ),
            "gates": (("compatible_observation", "fail"),),
            "rejections": rejections,
            "examples": examples,
            "citations": (),
            "eligible": False,
        }

    accepted_qnames = {item.fact.concept_key for item in accepted}
    candidate_relationships = tuple(candidate["relationships"])
    evidences = tuple(
        evidence for qname in accepted_qnames if (evidence := concept_evidence.get(qname))
    )
    aliases = {_normalized_name(alias) for alias in target.aliases}
    aliases.add(_normalized_name(target.metric_name))
    role_score, role_citations = _statement_role_score(
        target.statement_type, candidate_relationships
    )
    presentation_score, presentation_citations = _network_score(
        "presentation", aliases, accepted_qnames, candidate_relationships
    )
    relationship_score, relationship_citations = _relationship_score(
        aliases, accepted_qnames, candidate_relationships
    )
    accessions = tuple(sorted({item.accession_number for item in accepted}))
    recurrence_score = 2 if len(accessions) >= 2 else 1
    lexical_score, lexical_citations = _lexical_score(
        aliases, candidate_key, evidences
    )
    citations = tuple(
        dict.fromkeys(
            (
                *role_citations,
                *presentation_citations,
                *relationship_citations,
                f"observed accessions: {', '.join(accessions)}",
                *lexical_citations,
            )
        )
    )
    scores = (
        role_score,
        presentation_score,
        relationship_score,
        recurrence_score,
        lexical_score,
    )
    total = sum(scores)
    has_target_specific_evidence = bool(
        presentation_score or relationship_score or lexical_score
    )
    if not has_target_specific_evidence:
        _record_rejection(
            rejections,
            examples,
            "insufficient_compatibility_evidence",
            str(candidate["display"]),
        )
    return {
        "candidate_key": candidate_key,
        "display": candidate["display"],
        "scores": scores,
        "total": total,
        "accepted": len(accepted),
        "rejected": len(observations) - len(accepted),
        "accessions": accessions,
        "rejected_accessions": tuple(sorted(rejected_accessions)),
        "all_accessions": tuple(
            sorted({item.accession_number for item in observations})
        ),
        "gates": (
            ("namespace_family_collision", "pass"),
            ("period_type", _filtered_gate(rejections, "period_type_incompatible")),
            ("numeric_kind", _filtered_gate(rejections, "numeric_kind_incompatible")),
            ("unit", _filtered_gate(rejections, "unit_incompatible")),
            ("balance", "not_evaluable_no_target_metadata"),
            ("dimensions", _filtered_gate(rejections, "dimensional_observation")),
            (
                "blocking_diagnostic",
                _filtered_gate(rejections, "blocking_arelle_diagnostic"),
            ),
            (
                "reconciliation_conflict",
                _filtered_gate(rejections, "unresolved_reconciliation_conflict"),
            ),
            (
                "target_specific_compatibility_evidence",
                "pass" if has_target_specific_evidence else "fail",
            ),
        ),
        "rejections": rejections,
        "examples": examples,
        "citations": citations,
        "eligible": has_target_specific_evidence,
    }


def _project_target_result(
    target: CanonicalMetricTarget,
    all_targets: tuple[CanonicalMetricTarget, ...],
    pair_rows: Mapping[tuple[str, str, str], Mapping[str, object]],
    global_rejections: Counter[str],
    global_examples: Mapping[str, list[str]],
) -> ArelleInferenceResult:
    target_pair_rows = [
        row
        for (metric, statement, _), row in pair_rows.items()
        if metric == target.metric_name
        and statement == target.statement_type
    ]
    rows = [row for row in target_pair_rows if bool(row["eligible"])]
    rows.sort(key=lambda row: (-int(row["total"]), str(row["display"])))
    if not rows:
        rejection_counts = Counter(global_rejections)
        rejection_examples = {
            key: list(value) for key, value in global_examples.items()
        }
        rejected_observations = 0
        rejected_accessions: set[str] = set()
        for row in target_pair_rows:
            rejection_counts.update(row["rejections"])
            rejected_observations += int(row["accepted"]) + int(row["rejected"])
            rejected_accessions.update(row["all_accessions"])
            for key, values in row["examples"].items():
                for value in values:
                    if value not in rejection_examples.setdefault(key, []):
                        rejection_examples[key].append(value)
        return ArelleInferenceResult(
            target_metric=target.metric_name,
            target_statement=target.statement_type,
            outcome="no_candidate",
            top_candidate_qname=None,
            top_candidate_score=0,
            runner_up_candidate_qname=None,
            runner_up_score=None,
            runner_up_citations=(),
            strongest_competing_target=None,
            strongest_competing_target_score=None,
            strongest_competing_target_citations=(),
            statement_role_score=0,
            presentation_neighborhood_score=0,
            relationship_network_score=0,
            cross_form_recurrence_score=0,
            governed_lexical_score=0,
            metric_candidate_margin=0,
            concept_target_margin=0,
            accepted_observation_count=0,
            rejected_observation_count=rejected_observations,
            accepted_accession_count=0,
            rejected_accession_count=len(rejected_accessions),
            observed_accessions=(),
            hard_gates=(("candidate_available", "fail"),),
            rejection_totals=tuple(sorted(rejection_counts.items())),
            rejection_examples=_freeze_examples(rejection_examples),
            citations=(),
            reason="No candidate survived the deterministic compatibility gates.",
        )

    top = rows[0]
    runner = rows[1] if len(rows) > 1 else None
    runner_score = int(runner["total"]) if runner else 0
    metric_margin = int(top["total"]) - runner_score
    candidate_key = str(top["candidate_key"])
    competing: list[tuple[CanonicalMetricTarget, Mapping[str, object]]] = []
    for other in all_targets:
        if (other.metric_name, other.statement_type) == (
            target.metric_name,
            target.statement_type,
        ):
            continue
        row = pair_rows.get((other.metric_name, other.statement_type, candidate_key))
        if row is not None and bool(row["eligible"]):
            competing.append((other, row))
    competing.sort(
        key=lambda item: (-int(item[1]["total"]), item[0].metric_name, item[0].statement_type)
    )
    competitor_target, competitor_row = competing[0] if competing else (None, None)
    competitor_score = int(competitor_row["total"]) if competitor_row else 0
    concept_margin = int(top["total"]) - competitor_score
    outcome = (
        "unique_top_candidate"
        if metric_margin > 0 and concept_margin > 0
        else "needs_review"
    )
    rejection_counts = Counter(global_rejections)
    rejection_examples = {key: list(value) for key, value in global_examples.items()}
    rejection_counts.update(top["rejections"])
    for key, values in top["examples"].items():
        rejection_examples.setdefault(key, []).extend(values)
    scores = tuple(int(value) for value in top["scores"])
    return ArelleInferenceResult(
        target_metric=target.metric_name,
        target_statement=target.statement_type,
        outcome=outcome,
        top_candidate_qname=str(top["display"]),
        top_candidate_score=int(top["total"]),
        runner_up_candidate_qname=str(runner["display"]) if runner else None,
        runner_up_score=int(runner["total"]) if runner else None,
        runner_up_citations=tuple(runner["citations"]) if runner else (),
        strongest_competing_target=(
            f"{competitor_target.metric_name} ({competitor_target.statement_type})"
            if competitor_target
            else None
        ),
        strongest_competing_target_score=(
            int(competitor_row["total"]) if competitor_row else None
        ),
        strongest_competing_target_citations=(
            tuple(competitor_row["citations"]) if competitor_row else ()
        ),
        statement_role_score=scores[0],
        presentation_neighborhood_score=scores[1],
        relationship_network_score=scores[2],
        cross_form_recurrence_score=scores[3],
        governed_lexical_score=scores[4],
        metric_candidate_margin=metric_margin,
        concept_target_margin=concept_margin,
        accepted_observation_count=int(top["accepted"]),
        rejected_observation_count=int(top["rejected"]),
        accepted_accession_count=len(tuple(top["accessions"])),
        rejected_accession_count=len(tuple(top["rejected_accessions"])),
        observed_accessions=tuple(top["accessions"]),
        hard_gates=tuple(top["gates"]),
        rejection_totals=tuple(sorted(rejection_counts.items())),
        rejection_examples=_freeze_examples(rejection_examples),
        citations=tuple(top["citations"]),
        reason=(
            "Candidate is the unique best match in both target-to-concept and concept-to-target comparisons."
            if outcome == "unique_top_candidate"
            else "The top score is tied or the same concept is not uniquely best for this target."
        ),
    )


def _statement_role_score(
    statement_type: str,
    relationships: tuple[RelationshipEdge, ...],
) -> tuple[int, tuple[str, ...]]:
    keywords = _ROLE_KEYWORDS.get(statement_type, ())
    matching_roles = sorted(
        {
            edge.link_role
            for edge in relationships
            if any(keyword in edge.link_role.lower() for keyword in keywords)
        }
    )
    if matching_roles:
        return 2, (f"governed statement role: {matching_roles[0]}",)
    any_roles = sorted(
        {
            edge.link_role
            for edge in relationships
        }
    )
    if any_roles and keywords:
        return 0, (f"role did not match governed {statement_type} allowlist",)
    return 0, ()


def _network_score(
    network_kind: str,
    target_aliases: set[str],
    qnames: set[QNameKey],
    relationships: tuple[RelationshipEdge, ...],
) -> tuple[int, tuple[str, ...]]:
    relevant = [
        edge
        for edge in relationships
        if edge.network_kind == network_kind
        and (edge.from_concept in qnames or edge.to_concept in qnames)
    ]
    direct = [
        edge
        for edge in relevant
        if _normalized_name(
            edge.to_concept.local_name
            if edge.from_concept in qnames
            else edge.from_concept.local_name
        )
        in target_aliases
    ]
    if direct:
        edge = direct[0]
        return 2, (
            f"{network_kind} edge: {_display_qname(edge.from_concept)} -> {_display_qname(edge.to_concept)}",
        )
    return 0, ()


def _relationship_score(
    target_aliases: set[str],
    qnames: set[QNameKey],
    relationships: tuple[RelationshipEdge, ...],
) -> tuple[int, tuple[str, ...]]:
    scored: list[tuple[int, RelationshipEdge]] = []
    for kind in ("calculation", "definition"):
        score, _ = _network_score(kind, target_aliases, qnames, relationships)
        if score:
            edge = next(
                edge
                for edge in relationships
                if edge.network_kind == kind
                and (edge.from_concept in qnames or edge.to_concept in qnames)
                and _normalized_name(
                    edge.to_concept.local_name
                    if edge.from_concept in qnames
                    else edge.from_concept.local_name
                )
                in target_aliases
            )
            scored.append((score, edge))
    if not scored:
        return 0, ()
    score, edge = max(scored, key=lambda item: item[0])
    return score, (
        f"{edge.network_kind} edge: {_display_qname(edge.from_concept)} -> {_display_qname(edge.to_concept)}",
    )


def _lexical_score(
    target_aliases: set[str],
    candidate_key: str,
    evidences: tuple[ConceptEvidence, ...],
) -> tuple[int, tuple[str, ...]]:
    if candidate_key in target_aliases:
        return 2, ("candidate local name exactly matches a governed target alias",)
    evidence_texts = tuple(
        text
        for evidence in evidences
        for text in (evidence.standard_label, evidence.documentation)
        if text
    )
    normalized_texts = tuple(_normalized_name(text) for text in evidence_texts)
    alias_tokens = [set(_tokens(alias)) for alias in target_aliases if _tokens(alias)]
    for raw_text, normalized_text in zip(evidence_texts, normalized_texts):
        text_tokens = set(_tokens(normalized_text))
        if any(tokens and tokens.issubset(text_tokens) for tokens in alias_tokens):
            return 1, (f"governed lexical evidence: {raw_text}",)
    return 0, ()


def _expected_period_type(statement_type: str) -> str | None:
    if statement_type == "balance_sheet":
        return "instant"
    if statement_type in {"income_statement", "cash_flow_statement", "statement_of_equity"}:
        return "duration"
    return None


def _namespace_family(namespace_uri: str) -> str:
    parsed = urlparse(namespace_uri)
    host = (parsed.hostname or "").lower()
    if host in _STANDARD_NAMESPACE_HOSTS:
        return _STANDARD_NAMESPACE_HOSTS[host]
    if host.endswith("fasb.org"):
        return "us-gaap"
    if host:
        return f"issuer:{host}"
    return f"namespace:{namespace_uri}"


def _taxonomy_family(namespace_uri: str) -> str:
    family = _namespace_family(namespace_uri)
    return family.removeprefix("issuer:").split(":", 1)[-1]


def _display_qname(qname: QNameKey) -> str:
    if qname.prefix:
        return f"{qname.prefix}:{qname.local_name}"
    return f"{{{qname.namespace_uri}}}{qname.local_name}"


def _normalized_name(value: str) -> str:
    return "".join(_tokens(value))


def _tokens(value: str) -> tuple[str, ...]:
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return tuple(re.findall(r"[a-z0-9]+", expanded.lower()))


def _record_rejection(
    counts: Counter[str],
    examples: dict[str, list[str]],
    reason: str,
    example: str,
) -> None:
    counts[reason] += 1
    if example not in examples[reason] and len(examples[reason]) < 3:
        examples[reason].append(example)


def _filtered_gate(rejections: Counter[str], reason: str) -> str:
    return "pass_after_filter" if rejections[reason] else "pass"


def _freeze_examples(
    examples: Mapping[str, Iterable[str]],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple(
        (reason, tuple(dict.fromkeys(values))[:3])
        for reason, values in sorted(examples.items())
    )
