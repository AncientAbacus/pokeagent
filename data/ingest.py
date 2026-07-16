"""
Data Ingestion Module for PokeAgent
=====================================

This script fetches Pokemon data from PokeAPI and populates:
1. SQLite database with structured data (stats, types, moves, abilities)
2. Local cache to avoid re-fetching from the API

Key PokeAPI Knowledge:
- Rate limit: 100 requests/minute (unauthenticated)
- Pokemon endpoint: /api/v2/pokemon (list) and /api/v2/pokemon/{id} (detail)
- Species endpoint: /api/v2/pokemon-species/{id} (flavor text, generation info)
- Flavor text filtering: English only, deduplicated across game versions
"""

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Optional, Dict, List, Any

import requests
from dotenv import load_dotenv

load_dotenv()

# Configuration from environment or defaults
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "./data/pokeagent.db")
RAW_CACHE_DIR = Path("./data/raw")
POKEAPI_BASE = "https://pokeapi.co/api/v2"
RATE_LIMIT_REQUESTS = 100  # requests per minute
RATE_LIMIT_DELAY = 60 / RATE_LIMIT_REQUESTS  # seconds between requests

# Initialize cache directory
RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)


class PokemonDataIngestor:
    """Handles PokeAPI fetch and SQLite ingestion with smart caching."""

    def __init__(self, db_path: str = SQLITE_DB_PATH):
        """
        Initialize the ingestor.
        
        Args:
            db_path: Path to SQLite database (creates if not exists)
        """
        self.db_path = db_path
        self.session = requests.Session()
        self.request_count = 0
        self.last_request_time = 0
        
    def _respect_rate_limit(self) -> None:
        """Enforce rate limiting: 100 requests/min = ~0.6s between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        self.last_request_time = time.time()
    
    def _get_cache_path(self, endpoint: str) -> Path:
        """Convert API endpoint to local cache file path."""
        # Example: /api/v2/pokemon/1 → ./data/raw/pokemon_1.json
        clean_endpoint = endpoint.replace(f"{POKEAPI_BASE}/", "").replace("/", "_")
        return RAW_CACHE_DIR / f"{clean_endpoint}.json"
    
    def _fetch_from_api(self, endpoint: str, use_cache: bool = True) -> Optional[Dict]:
        """
        Fetch from PokeAPI with caching.
        
        Args:
            endpoint: Full PokeAPI endpoint URL
            use_cache: If True, use local cache; if False, always fetch fresh
            
        Returns:
            Parsed JSON response or None if failed
        """
        cache_path = self._get_cache_path(endpoint)
        
        # Try cache first if enabled
        if use_cache and cache_path.exists():
            with open(cache_path, "r") as f:
                return json.load(f)
        
        # Fetch from API with rate limiting
        self._respect_rate_limit()
        try:
            response = self.session.get(endpoint, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Save to cache for future runs
            with open(cache_path, "w") as f:
                json.dump(data, f, indent=2)
            
            return data
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching {endpoint}: {e}")
            return None
    
    def _init_database(self) -> sqlite3.Connection:
        """Create SQLite database from schema.sql."""
        conn = sqlite3.connect(self.db_path)
        schema_path = Path("./data/schema.sql")
        
        if schema_path.exists():
            with open(schema_path, "r") as f:
                conn.executescript(f.read())
            print(f"✓ Database initialized: {self.db_path}")
        else:
            print(f"⚠ schema.sql not found at {schema_path}")
        
        return conn
    
    def ingest_pokemon_list(self, limit: int = 100, offset: int = 0) -> Optional[List[Dict]]:
        """
        Fetch pokemon list from PokeAPI.
        
        Args:
            limit: Number of pokemon to fetch (max 1025)
            offset: Pagination offset
            
        Returns:
            List of pokemon dicts with id, name, url
        """
        endpoint = f"{POKEAPI_BASE}/pokemon?limit={limit}&offset={offset}"
        data = self._fetch_from_api(endpoint)
        
        if data:
            print(f"✓ Fetched {len(data['results'])} pokemon")
            return data['results']
        return None
    
    def ingest_pokemon_detail(self, pokemon_id_or_name: str) -> Optional[Dict]:
        """
        Fetch detailed pokemon data (stats, types, moves, abilities).
        
        Args:
            pokemon_id_or_name: Pokemon ID (int) or name (str)
            
        Returns:
            Pokemon detail dict or None
        """
        endpoint = f"{POKEAPI_BASE}/pokemon/{pokemon_id_or_name}"
        return self._fetch_from_api(endpoint)
    
    def ingest_pokemon_species(self, pokemon_id_or_name: str) -> Optional[Dict]:
        """
        Fetch pokemon species data (flavor text, generation, evolution chain).
        
        Args:
            pokemon_id_or_name: Pokemon ID (int) or name (str)
            
        Returns:
            Species dict or None
        """
        endpoint = f"{POKEAPI_BASE}/pokemon-species/{pokemon_id_or_name}"
        return self._fetch_from_api(endpoint)
    
    def extract_flavor_text_entries(self, species_data: Dict) -> List[Dict]:
        """
        Extract English flavor text from species data, deduplicating across game versions.
        
        Why separate function?
        - Flavor text often repeats across game versions (e.g., Red vs Blue)
        - We deduplicate by text content to avoid redundant RAG vectors
        - Each entry becomes one RAG chunk with metadata
        
        Args:
            species_data: Dict from pokemon-species endpoint
            
        Returns:
            List of {flavor_text, game_version, generation}
        """
        entries = []
        seen_texts = set()
        
        if "flavor_text_entries" not in species_data:
            return entries
        
        for entry in species_data.get("flavor_text_entries", []):
            # Filter to English only
            if entry.get("language", {}).get("name") != "en":
                continue
            
            text = entry.get("flavor_text", "").strip()
            
            # Skip duplicates (same text in different game versions)
            if text in seen_texts or not text:
                continue
            
            seen_texts.add(text)
            
            # Determine generation from game version
            game_version = entry.get("version", {}).get("name", "unknown")
            generation = self._game_version_to_generation(game_version)
            
            entries.append({
                "flavor_text": text,
                "game_version": game_version,
                "generation": generation,
            })
        
        return entries
    
    @staticmethod
    def _game_version_to_generation(game_version: str) -> int:
        """Map game version string to generation number."""
        # Simplified mapping; full version would include all 1000+ game versions
        gen_mapping = {
            # Gen 1
            "red": 1, "blue": 1, "yellow": 1,
            # Gen 2
            "gold": 2, "silver": 2, "crystal": 2,
            # Gen 3
            "ruby": 3, "sapphire": 3, "emerald": 3,
            # Gen 4
            "diamond": 4, "pearl": 4, "platinum": 4,
            # etc.
        }
        # Extract first word of game version for matching
        first_word = game_version.split("-")[0].lower()
        return gen_mapping.get(first_word, 0)
    
    def insert_pokemon_to_db(self, poke_detail: Dict, poke_species: Dict, conn: sqlite3.Connection) -> bool:
        """
        Insert pokemon into all relevant tables.
        
        Args:
            poke_detail: From /pokemon/{id} endpoint
            poke_species: From /pokemon-species/{id} endpoint
            conn: SQLite connection
            
        Returns:
            True if successful, False otherwise
        """
        try:
            cursor = conn.cursor()
            
            # Extract main pokemon info
            poke_id = poke_detail.get("id")
            name = poke_detail.get("name")
            
            # Insert main pokemon record
            national_dex = poke_species.get("id", poke_id)
            cursor.execute("""
                INSERT OR IGNORE INTO pokemon 
                (id, national_dex_number, name, height_dm, weight_hg, is_default)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                poke_id,
                national_dex,
                name,
                poke_detail.get("height"),
                poke_detail.get("weight"),
                poke_detail.get("is_default", True)
            ))
            
            # Insert stats
            stats_by_name = {s["stat"]["name"]: s["base_stat"] for s in poke_detail.get("stats", [])}
            cursor.execute("""
                INSERT OR IGNORE INTO pokemon_stats
                (pokemon_id, hp, attack, defense, sp_atk, sp_def, speed)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                poke_id,
                stats_by_name.get("hp", 0),
                stats_by_name.get("attack", 0),
                stats_by_name.get("defense", 0),
                stats_by_name.get("special-attack", 0),
                stats_by_name.get("special-defense", 0),
                stats_by_name.get("speed", 0)
            ))
            
            # Insert types
            for type_info in poke_detail.get("types", []):
                cursor.execute("""
                    INSERT OR IGNORE INTO pokemon_types
                    (pokemon_id, type_name, slot)
                    VALUES (?, ?, ?)
                """, (
                    poke_id,
                    type_info["type"]["name"],
                    type_info["slot"]
                ))
            
            # Insert abilities
            for ability_info in poke_detail.get("abilities", []):
                cursor.execute("""
                    INSERT OR IGNORE INTO pokemon_abilities
                    (pokemon_id, ability_name, is_hidden)
                    VALUES (?, ?, ?)
                """, (
                    poke_id,
                    ability_info["ability"]["name"],
                    ability_info.get("is_hidden", False)
                ))
            
            # Insert moves
            for move_info in poke_detail.get("moves", []):
                cursor.execute("""
                    INSERT OR IGNORE INTO pokemon_moves
                    (pokemon_id, move_name, learn_method)
                    VALUES (?, ?, ?)
                """, (
                    poke_id,
                    move_info["move"]["name"],
                    move_info["version_group_details"][0]["move_learn_method"]["name"] if move_info.get("version_group_details") else "unknown"
                ))
            
            # Insert flavor text entries
            flavor_entries = self.extract_flavor_text_entries(poke_species)
            for entry in flavor_entries:
                cursor.execute("""
                    INSERT OR IGNORE INTO pokemon_flavor_text
                    (pokemon_id, pokemon_name, national_dex_number, flavor_text, game_version, generation)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    poke_id,
                    name,
                    national_dex,
                    entry["flavor_text"],
                    entry["game_version"],
                    entry["generation"]
                ))
            
            conn.commit()
            return True
        except Exception as e:
            print(f"❌ Error inserting pokemon {name}: {e}")
            return False
    
    def run_ingestion(self, num_pokemon: int = 100) -> None:
        """
        Run the full ingestion pipeline.
        
        Args:
            num_pokemon: How many pokemon to ingest (start small for testing)
        """
        print(f"\n{'='*60}")
        print(f"PokeAgent Data Ingestion")
        print(f"{'='*60}\n")
        
        # Initialize database
        conn = self._init_database()
        
        # Fetch pokemon list
        pokemon_list = self.ingest_pokemon_list(limit=num_pokemon)
        if not pokemon_list:
            print("❌ Failed to fetch pokemon list. Exiting.")
            conn.close()
            return
        
        # Process each pokemon
        for idx, poke_summary in enumerate(pokemon_list, 1):
            poke_name = poke_summary["name"]
            print(f"[{idx}/{len(pokemon_list)}] Ingesting {poke_name}...", end=" ")
            
            # Fetch detail view
            poke_detail = self.ingest_pokemon_detail(poke_name)
            if not poke_detail:
                print("❌ (detail fetch failed)")
                continue
            
            # Fetch species view (for flavor text)
            poke_species = self.ingest_pokemon_species(poke_name)
            if not poke_species:
                print("❌ (species fetch failed)")
                continue
            
            # Insert into database
            if self.insert_pokemon_to_db(poke_detail, poke_species, conn):
                flavor_count = len(self.extract_flavor_text_entries(poke_species))
                print(f"✓ ({flavor_count} flavor texts)")
            else:
                print("❌ (insert failed)")
        
        conn.close()
        print(f"\n{'='*60}")
        print(f"✓ Ingestion complete!")
        print(f"{'='*60}\n")


def main():
    """Entry point for data ingestion."""
    # Full Pokedex, including regional forms/megas (PokeAPI currently lists ~1351 entries)
    ingestor = PokemonDataIngestor(db_path=SQLITE_DB_PATH)
    ingestor.run_ingestion(num_pokemon=1400)


if __name__ == "__main__":
    main()
