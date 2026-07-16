"""
RAG Retriever Module
====================

Thin wrapper around PokemonEmbedder that provides a clean retrieval interface.
The embedder handles the ChromaDB details; this module exposes the query API.

Lazy initialization: the SentenceTransformer model is only loaded when first
queried, not at import time (keeps startup fast).
"""

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

_embedder_instance = None


def _get_embedder():
    """Lazy-load the embedder singleton."""
    global _embedder_instance
    if _embedder_instance is None:
        from rag.embedder import PokemonEmbedder
        logger.info("Initializing PokemonEmbedder (first retrieval)...")
        _embedder_instance = PokemonEmbedder()
    return _embedder_instance


def retrieve(
    query: str,
    k: int = 5,
    pokemon_filter: Optional[str] = None,
    generation_filter: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Retrieve relevant Pokemon flavor text entries via semantic search.

    Args:
        query: Natural language query (e.g., "Why does Cubone wear a skull?")
        k: Number of results to return
        pokemon_filter: Restrict results to a single Pokemon (e.g., "cubone")
        generation_filter: Restrict results to a specific generation number

    Returns:
        List of dicts with keys: pokemon_name, flavor_text, generation,
        game_version, distance (cosine distance — lower is more similar)

    Example:
        >>> results = retrieve("lonely Pokemon that misses its mother", k=3)
        >>> results[0]["pokemon_name"]
        'cubone'
    """
    embedder = _get_embedder()
    results = embedder.search(
        query=query,
        k=k,
        pokemon_filter=pokemon_filter,
        generation_filter=generation_filter
    )
    logger.info(f"retrieve('{query[:40]}...'): {len(results)} results")
    return results
