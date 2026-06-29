"""Prewarm semantic target XBRL concept candidate embeddings."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_settings
from src.processing import prewarm_all_target_candidate_embeddings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Precompute target XBRL concept candidate embeddings for common "
            "base and all hard-industry target concepts."
        )
    )
    parser.add_argument(
        "--env-file",
        default="config.env",
        help="Environment file containing retrieval embedding settings.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Do not print the concise prewarm summary.",
    )
    args = parser.parse_args(argv)

    settings = load_settings(args.env_file)
    result = prewarm_all_target_candidate_embeddings(
        embedding_model_name=settings.retrieval_embedding_model,
        model_cache_dir=settings.knowledge_storage_dir / "model_cache" / "fastembed",
        target_embedding_path=(
            settings.knowledge_storage_dir
            / "concept_mapping"
            / "target_embeddings.json"
        ),
    )
    if not args.quiet:
        print(
            "\n".join(
                (
                    "Target embedding prewarm summary",
                    f"Embedding model: {result.embedding_model_name}",
                    f"Canonical targets: {result.target_count}",
                    f"Target XBRL concept candidates: {result.target_candidate_count}",
                    f"Cached vectors: {result.cached_vector_count}",
                    f"Reused vectors: {result.reused_vector_count}",
                    f"Created vectors: {result.created_vector_count}",
                    f"Cache path: {result.cache_path}",
                )
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
