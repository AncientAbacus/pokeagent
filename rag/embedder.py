"""
RAG Embedder Module
===================

Converts Pokemon flavor text into embeddings and stores in ChromaDB.

Key Concepts:
- Embeddings: Convert text to 384-dim vectors (sentence-transformers all-MiniLM-L6-v2)
- ChromaDB: Local vector database for fast semantic search
- Metadata: Store pokemon_name, generation, game_version with each chunk for filtering
- Distance metric: Cosine similarity (how "close" are two text meanings?)

Why this model?
- all-MiniLM-L6-v2 is 22MB (fast), 384-dim (good quality/speed tradeoff)
- Alternative: OpenAI embeddings (slower but more accurate; requires API key)
"""

import sqlite3
import os
from typing import List, Dict, Any, Optional
from pathlib import Path
import logging

from dotenv import load_dotenv

# ChromaDB for vector storage
import chromadb

# Embeddings
from sentence_transformers import SentenceTransformer

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Configuration
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./rag/chroma_db")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "./data/pokeagent.db")
COLLECTION_NAME = "pokemon_lore"


class PokemonEmbedder:
    """Embed Pokemon flavor text and store in ChromaDB."""
    
    def __init__(
        self,
        model_name: str = EMBEDDING_MODEL_NAME,
        chroma_dir: str = CHROMA_PERSIST_DIR,
        db_path: str = SQLITE_DB_PATH
    ):
        """
        Initialize embedder.
        
        Args:
            model_name: HuggingFace sentence-transformers model
            chroma_dir: Directory for ChromaDB persistence
            db_path: SQLite database path
        """
        self.model_name = model_name
        self.chroma_dir = chroma_dir
        self.db_path = db_path
        
        # Create chroma dir
        Path(chroma_dir).mkdir(parents=True, exist_ok=True)
        
        # Load embedding model (downloads on first run, cached after)
        logger.info(f"Loading embedding model: {model_name}")
        self.model = SentenceTransformer(model_name)
        logger.info(f"✓ Model loaded (embedding dimension: {self.model.get_sentence_embedding_dimension()})")
        
        # Initialize ChromaDB (modern API)
        self.client = chromadb.PersistentClient(path=chroma_dir)
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={
                "description": "Pokemon lore & flavor text",
                "hnsw:space": "cosine",  # Chroma defaults to L2
            }
        )
        logger.info(f"✓ ChromaDB collection ready: {COLLECTION_NAME}")
    
    def fetch_flavor_texts_from_db(self) -> List[Dict[str, Any]]:
        """
        Fetch all flavor texts from SQLite.
        
        Returns:
            List of dicts: {id, pokemon_name, flavor_text, generation, game_version}
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Return dicts instead of tuples
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                id,
                pokemon_name,
                flavor_text,
                generation,
                game_version,
                national_dex_number
            FROM pokemon_flavor_text
            ORDER BY pokemon_name, generation
        """)
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Convert texts to embeddings.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors (384-dim for all-MiniLM-L6-v2)
        """
        embeddings = self.model.encode(texts, convert_to_tensor=False)
        return embeddings.tolist() if hasattr(embeddings, 'tolist') else [e.tolist() for e in embeddings]
    
    def populate_embeddings(self, batch_size: int = 100) -> int:
        """
        Fetch all flavor texts from SQLite and embed them into ChromaDB.
        
        Args:
            batch_size: Process in batches to manage memory
            
        Returns:
            Number of embeddings added
        """
        logger.info("Fetching flavor texts from SQLite...")
        flavor_texts = self.fetch_flavor_texts_from_db()
        logger.info(f"✓ Found {len(flavor_texts)} flavor text entries")
        
        if not flavor_texts:
            logger.warning("No flavor texts found in database!")
            return 0
        
        # Get existing IDs in ChromaDB to avoid duplicates
        existing_count = self.collection.count()
        logger.info(f"ChromaDB already has {existing_count} embeddings")
        
        # Batch embed and add to ChromaDB
        added_count = 0
        for i in range(0, len(flavor_texts), batch_size):
            batch = flavor_texts[i:i+batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(flavor_texts) + batch_size - 1) // batch_size
            
            # Extract texts and metadata
            texts = [entry["flavor_text"] for entry in batch]
            ids = [f"flavor_{entry['id']}" for entry in batch]
            metadatas = [
                {
                    "pokemon_name": entry["pokemon_name"],
                    "generation": str(entry["generation"]) if entry["generation"] else "0",
                    "game_version": entry["game_version"],
                    "national_dex_number": str(entry["national_dex_number"])
                }
                for entry in batch
            ]
            
            # Embed and add to collection
            embeddings = self.embed_texts(texts)
            self.collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas
            )
            
            added_count += len(batch)
            progress = f"[{batch_num}/{total_batches}] Embedded {added_count}/{len(flavor_texts)} texts"
            logger.info(progress)
        
        logger.info(f"✓ Persisted to {self.chroma_dir}")
        
        return added_count
    
    def search(
        self,
        query: str,
        k: int = 5,
        generation_filter: Optional[int] = None,
        pokemon_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant flavor texts using semantic similarity.
        
        Args:
            query: Natural language query (e.g., "origins of Pikachu")
            k: Number of results to return
            generation_filter: Filter to specific Pokemon generation (optional)
            pokemon_filter: Filter to specific Pokemon name (optional)
            
        Returns:
            List of {pokemon_name, flavor_text, generation, distance}
        """
        # Build where filter (Chroma requires $and for more than one condition)
        conditions = []
        if generation_filter is not None:
            conditions.append({"generation": str(generation_filter)})
        if pokemon_filter is not None:
            conditions.append({"pokemon_name": pokemon_filter.lower()})
        where_filter = None
        if len(conditions) == 1:
            where_filter = conditions[0]
        elif conditions:
            where_filter = {"$and": conditions}
        
        # Embed the query with the same model used for the documents
        results = self.collection.query(
            query_embeddings=self.embed_texts([query]),
            n_results=k,
            where=where_filter
        )
        
        # Format results
        formatted = []
        if results["documents"] and results["documents"][0]:
            for doc, metadata, distance in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0]
            ):
                formatted.append({
                    "pokemon_name": metadata["pokemon_name"],
                    "flavor_text": doc,
                    "generation": int(metadata["generation"]),
                    "game_version": metadata["game_version"],
                    "distance": distance  # cosine distance; lower is better
                })
        
        return formatted


def main():
    """Test the embedder."""
    embedder = PokemonEmbedder()
    
    # Populate embeddings
    logger.info("\n" + "="*60)
    logger.info("Populating ChromaDB with Pokemon flavor texts")
    logger.info("="*60)
    
    added = embedder.populate_embeddings()
    logger.info(f"\n✓ Successfully embedded {added} flavor texts\n")
    
    # Test semantic search
    logger.info("Testing semantic search...")
    logger.info("="*60)
    
    test_queries = [
        "What is Pikachu's origin and nature?",
        "Water type creatures",
        "Evolution and growth"
    ]
    
    for query in test_queries:
        results = embedder.search(query, k=3)
        print(f"\n📌 Query: '{query}'")
        for i, result in enumerate(results, 1):
            print(f"\n  {i}. {result['pokemon_name']} (Gen {result['generation']})")
            print(f"     {result['flavor_text'][:80]}...")
            print(f"     [Distance: {result['distance']:.3f}]")


if __name__ == "__main__":
    main()
