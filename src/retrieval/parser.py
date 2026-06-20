"""Form-aware extraction of visible SEC filing sections from Inline XBRL HTML."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from lxml import etree, html

from src.retrieval.errors import EmptyFilingTextError, FilingParseError
from src.retrieval.models import ParsedFiling, ParsedSection

PARSER_VERSION = "sec-html-items-v3"
MIN_SECTION_CHARACTERS = 80
MIN_CLASSIFIED_RATIO = 0.35
MAX_HEADING_CHARACTERS = 240

_WHITESPACE_RE = re.compile(r"[\t\f\v ]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_PART_RE = re.compile(r"^part\s+(i{1,3}|iv|v|vi{0,3}|ix|x)\b", re.IGNORECASE)
_ITEM_RE = re.compile(
    r"^item\s+(?P<number>\d{1,2})(?P<suffix>[a-z]?)\s*[.\-:–—]?\s*(?P<title>.*)$",
    re.IGNORECASE,
)

_TEN_K_SECTIONS = {
    "1": ("business", 10),
    "1A": ("risk_factors", 20),
    "1B": ("unresolved_staff_comments", 30),
    "1C": ("cybersecurity", 40),
    "2": ("properties", 50),
    "3": ("legal_proceedings", 60),
    "4": ("mine_safety_disclosures", 70),
    "5": ("market_for_equity", 80),
    "6": ("reserved", 90),
    "7": ("management_discussion_and_analysis", 100),
    "7A": ("market_risk", 110),
    "8": ("financial_statements_and_notes", 120),
    "9": ("accounting_disagreements", 130),
    "9A": ("controls_and_procedures", 140),
    "9B": ("other_information", 150),
    "9C": ("foreign_jurisdiction_disclosures", 160),
    "10": ("directors_and_governance", 170),
    "11": ("executive_compensation", 180),
    "12": ("security_ownership", 190),
    "13": ("relationships_and_independence", 200),
    "14": ("principal_accountant_fees", 210),
    "15": ("exhibits_and_financial_statement_schedules", 220),
    "16": ("form_10k_summary", 230),
}

_TEN_Q_SECTIONS = {
    ("I", "1"): ("financial_statements_and_notes", 10),
    ("I", "2"): ("management_discussion_and_analysis", 20),
    ("I", "3"): ("market_risk", 30),
    ("I", "4"): ("controls_and_procedures", 40),
    ("II", "1"): ("legal_proceedings", 50),
    ("II", "1A"): ("risk_factors", 60),
    ("II", "2"): ("unregistered_sales", 70),
    ("II", "3"): ("defaults_upon_senior_securities", 80),
    ("II", "4"): ("mine_safety_disclosures", 90),
    ("II", "5"): ("other_information", 100),
    ("II", "6"): ("exhibits", 110),
}


@dataclass(frozen=True)
class _TextBlock:
    text: str
    tag: str


@dataclass(frozen=True)
class _HeadingCandidate:
    block_index: int
    section_name: str
    section_order: int
    title: str


def parse_filing_html(path: Path, form_type: str) -> ParsedFiling:
    """Parse one local 10-K or 10-Q HTML filing into visible SEC sections."""
    try:
        source = path.read_bytes()
    except OSError as exc:
        raise FilingParseError(f"Could not read filing HTML at {path}: {exc}") from exc

    source_sha256 = hashlib.sha256(source).hexdigest()
    parser = html.HTMLParser(
        recover=True,
        no_network=True,
        remove_comments=True,
        huge_tree=True,
    )
    try:
        decoded_source = source.decode("utf-8-sig", errors="replace")
        decoded_source = re.sub(
            r"^\s*<\?xml[^>]*\?>",
            "",
            decoded_source,
            count=1,
            flags=re.IGNORECASE,
        )
        root = html.fromstring(decoded_source, parser=parser)
    except (etree.ParserError, ValueError) as exc:
        raise FilingParseError(f"Could not parse filing HTML at {path}: {exc}") from exc

    _remove_non_visible_elements(root)
    blocks = _extract_text_blocks(root)
    full_text = _normalize_multiline("\n".join(block.text for block in blocks))
    if not full_text:
        raise EmptyFilingTextError(f"Filing {path} contained no visible indexable text")

    normalized_form = form_type.strip().upper()
    candidates = _find_heading_candidates(blocks, normalized_form)
    sections = _select_sections(blocks, candidates)
    classified_characters = sum(len(section.text) for section in sections)
    classified_ratio = classified_characters / max(len(full_text), 1)
    warnings: list[str] = []

    if not sections or classified_ratio < MIN_CLASSIFIED_RATIO:
        if sections:
            warnings.append(
                f"Section detection covered only {classified_ratio:.1%} of visible text; "
                "used full-filing fallback"
            )
        else:
            warnings.append("No reliable SEC item headings were detected; used full-filing fallback")
        return ParsedFiling(
            source_sha256=source_sha256,
            sections=(
                ParsedSection(
                    name="unclassified_full_filing",
                    title="Unclassified full filing",
                    order=0,
                    text=full_text,
                ),
            ),
            warnings=tuple(warnings),
            used_fallback=True,
        )

    return ParsedFiling(
        source_sha256=source_sha256,
        sections=tuple(sections),
        warnings=tuple(warnings),
        used_fallback=False,
    )


def sha256_file(path: Path) -> str:
    """Return a filing source hash without loading the entire file into memory."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise FilingParseError(f"Could not hash filing HTML at {path}: {exc}") from exc
    return digest.hexdigest()


def _remove_non_visible_elements(root: html.HtmlElement) -> None:
    removable: list[html.HtmlElement] = []
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        tag = element.tag.lower()
        local_tag = tag.rsplit("}", 1)[-1].rsplit(":", 1)[-1]
        style = re.sub(r"\s+", "", (element.get("style") or "").lower())
        is_ix_hidden = tag.endswith(":hidden") or tag.endswith("}hidden")
        is_ix_header = tag.endswith(":header") or tag.endswith("}header")
        if (
            local_tag in {"script", "style", "noscript"}
            or is_ix_hidden
            or is_ix_header
            or element.get("hidden") is not None
            or (element.get("aria-hidden") or "").lower() == "true"
            or "display:none" in style
            or "visibility:hidden" in style
        ):
            removable.append(element)
    for element in reversed(removable):
        parent = element.getparent()
        if parent is not None:
            parent.remove(element)


def _extract_text_blocks(root: html.HtmlElement) -> list[_TextBlock]:
    blocks: list[_TextBlock] = []
    block_tags = {"div", "p", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        tag = element.tag.lower().rsplit("}", 1)[-1].rsplit(":", 1)[-1]
        if tag not in block_tags:
            continue
        if tag == "div" and any(
            isinstance(child.tag, str)
            and child.tag.lower().rsplit("}", 1)[-1].rsplit(":", 1)[-1] in block_tags
            for child in element.iterdescendants()
        ):
            continue
        if tag == "tr":
            cells = [
                _normalize_inline(cell.text_content())
                for cell in element.xpath("./th|./td")
                if _normalize_inline(cell.text_content())
            ]
            text = " | ".join(cells)
        else:
            text = _normalize_inline(element.text_content())
        if text:
            blocks.append(_TextBlock(text=text, tag=tag))

    if blocks:
        return blocks
    body = root.find("body")
    fallback_root = body if body is not None else root
    fallback = _normalize_multiline(fallback_root.text_content())
    return [_TextBlock(text=fallback, tag="body")] if fallback else []


def _find_heading_candidates(
    blocks: list[_TextBlock],
    form_type: str,
) -> list[_HeadingCandidate]:
    candidates: list[_HeadingCandidate] = []
    current_part = "I"
    for index, block in enumerate(blocks):
        text = block.text.strip()
        if len(text) > MAX_HEADING_CHARACTERS:
            continue
        part_match = _PART_RE.match(text)
        if part_match:
            current_part = _roman_part(part_match.group(1))
            continue
        item_match = _ITEM_RE.match(text)
        if item_match is None:
            continue
        item_key = f"{item_match.group('number')}{item_match.group('suffix').upper()}"
        title = item_match.group("title").strip(" .:-–—") or f"Item {item_key}"
        if form_type == "10-K":
            section = _TEN_K_SECTIONS.get(item_key)
        elif form_type == "10-Q":
            section = _TEN_Q_SECTIONS.get((current_part, item_key))
        else:
            section = None
        if section is None:
            continue
        candidates.append(
            _HeadingCandidate(
                block_index=index,
                section_name=section[0],
                section_order=section[1],
                title=title,
            )
        )
    return candidates


def _select_sections(
    blocks: list[_TextBlock],
    candidates: list[_HeadingCandidate],
) -> list[ParsedSection]:
    if not candidates:
        return []

    best_by_section: dict[str, tuple[int, int, _HeadingCandidate]] = {}
    for candidate_index, candidate in enumerate(candidates):
        next_index = (
            candidates[candidate_index + 1].block_index
            if candidate_index + 1 < len(candidates)
            else len(blocks)
        )
        span_size = sum(len(block.text) for block in blocks[candidate.block_index + 1 : next_index])
        heading_quality = _heading_quality(candidate.title)
        current = best_by_section.get(candidate.section_name)
        score = (heading_quality, span_size)
        if current is None or score > current[:2]:
            best_by_section[candidate.section_name] = (
                heading_quality,
                span_size,
                candidate,
            )

    selected = sorted(
        (value[2] for value in best_by_section.values()),
        key=lambda item: item.block_index,
    )
    sections: list[ParsedSection] = []
    for selected_index, candidate in enumerate(selected):
        next_index = (
            selected[selected_index + 1].block_index
            if selected_index + 1 < len(selected)
            else len(blocks)
        )
        text = _normalize_multiline(
            "\n".join(block.text for block in blocks[candidate.block_index + 1 : next_index])
        )
        if len(text) < MIN_SECTION_CHARACTERS:
            continue
        sections.append(
            ParsedSection(
                name=candidate.section_name,
                title=candidate.title,
                order=candidate.section_order,
                text=text,
            )
        )
    return sections


def _heading_quality(title: str) -> int:
    normalized = title.strip()
    if not normalized:
        return 0
    if "|" in normalized or normalized[0] in {",", ".", ":", ";"}:
        return 0
    if re.fullmatch(r"Item\s+\d{1,2}[A-Z]?", normalized, re.IGNORECASE):
        return 0
    return 1 if sum(character.isalpha() for character in normalized) >= 4 else 0


def _roman_part(value: str) -> str:
    normalized = value.upper()
    return "II" if normalized == "II" else "I"


def _normalize_inline(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value.replace("\xa0", " ")).strip()


def _normalize_multiline(value: str) -> str:
    lines = [_normalize_inline(line) for line in value.splitlines()]
    return _BLANK_LINES_RE.sub("\n\n", "\n".join(line for line in lines if line)).strip()
