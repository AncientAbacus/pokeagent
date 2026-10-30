"""
Data Ingestion Module for PokeAgent
=====================================

This script fetches Pokemon data from PokeAPI and populates:
1. SQLite database with structured data (stats, types, moves, abilities)
2. Local cache to avoid re-fetching from the API

Key PokeAPI Knowledge:
- Rate limit: 100 requests/minute (unauthenticated)
- Pokemon endpoint: /api/v2/pokemon/{id} (stats, types, moves, abilities)
- Species endpoint: /api/v2/pokemon-species/{id} (flavor text, generation info)
- Flavor text filtering: English only, deduplicated across game versions
- Static mirror: PokeAPI publishes the same JSON at github.com/PokeAPI/api-data,
  used as a fallback when pokeapi.co is unreachable (no rate limit there)

Usage:
    python -m data.ingest              # Gen 1 (first 151 Pokemon)
    python -m data.ingest --limit 1025 # Full National Dex
"""

import argparse
import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Optional, Dict, List

import requests
from dotenv import load_dotenv

load_dotenv()

# Configuration from environment or defaults
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "./data/pokeagent.db")
RAW_CACHE_DIR = Path("./data/raw")
POKEAPI_BASE = os.getenv("POKEAPI_BASE", "https://pokeapi.co/api/v2")
POKEAPI_MIRROR_BASE = os.getenv(
    "POKEAPI_MIRROR_BASE",
    "https://raw.githubusercontent.com/PokeAPI/api-data/master/data/api/v2",
)
RATE_LIMIT_REQUESTS = 100  # requests per minute
RATE_LIMIT_DELAY = 60 / RATE_LIMIT_REQUESTS  # seconds between requests
DEFAULT_NUM_POKEMON = 151  # Gen 1; fast enough for local dev

# Game version -> generation the game was released in
VERSION_TO_GENERATION: Dict[str, int] = {
    "red": 1, "blue": 1, "yellow": 1,
    "gold": 2, "silver": 2, "crystal": 2,
    "ruby": 3, "sapphire": 3, "emerald": 3, "firered": 3, "leafgreen": 3,
    "colosseum": 3, "xd": 3,
    "diamond": 4, "pearl": 4, "platinum": 4, "heartgold": 4, "soulsilver": 4,
    "black": 5, "white": 5, "black-2": 5, "white-2": 5,
    "x": 6, "y": 6, "omega-ruby": 6, "alpha-sapphire": 6,
    "sun": 7, "moon": 7, "ultra-sun": 7, "ultra-moon": 7,
    "lets-go-pikachu": 7, "lets-go-eevee": 7,
    "sword": 8, "shield": 8, "brilliant-diamond": 8, "shining-pearl": 8,
    "legends-arceus": 8,
    "scarlet": 9, "violet": 9,
}

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
        self.last_request_time = 0
        # Flips to True after the first failed request to pokeapi.co
        self.use_mirror = False

    def _respect_rate_limit(self) -> None:
        """Enforce rate limiting: 100 requests/min = ~0.6s between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        self.last_request_time = time.time()

    def _get_cache_path(self, path: str) -> Path:
        """Convert an API path to a local cache file path."""
        # Example: pokemon/1 → ./data/raw/pokemon_1.json
        return RAW_CACHE_DIR / f"{path.strip('/').replace('/', '_')}.json"

    def _get_json(self, url: str) -> Dict:
        """GET a URL and return parsed JSON (raises on HTTP errors)."""
        response = self.session.get(url, timeout=10)
        response.raise_for_status()
        return response.json()

    def _fetch_from_api(self, path: str, use_cache: bool = True) -> Optional[Dict]:
        """
        Fetch from PokeAPI with caching, falling back to the static mirror.

        Args:
            path: API path relative to /api/v2 (e.g., "pokemon/25")
            use_cache: If True, use local cache; if False, always fetch fresh

        Returns:
            Parsed JSON response or None if failed
        """
        cache_path = self._get_cache_path(path)

        # Try cache first if enabled
        if use_cache and cache_path.exists():
            with open(cache_path, "r") as f:
                return json.load(f)

        data = None
        if not self.use_mirror:
            # Live API with rate limiting
            self._respect_rate_limit()
            try:
                data = self._get_json(f"{POKEAPI_BASE}/{path}")
            except requests.exceptions.RequestException as e:
                print(f"\n⚠ pokeapi.co unavailable ({e.__class__.__name__}); using static mirror")
                self.use_mirror = True

        if data is None:
            try:
                data = self._get_json(f"{POKEAPI_MIRROR_BASE}/{path}/index.json")
            except requests.exceptions.RequestException as e:
                print(f"❌ Error fetching {path}: {e}")
                return None

        # Save to cache for future runs
        with open(cache_path, "w") as f:
            json.dump(data, f, indent=2)

        return data

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

    def ingest_pokemon_detail(self, pokemon_id: int) -> Optional[Dict]:
        """
        Fetch detailed pokemon data (stats, types, moves, abilities).

        Args:
            pokemon_id: National Dex number

        Returns:
            Pokemon detail dict or None
        """
        return self._fetch_from_api(f"pokemon/{pokemon_id}")

    def ingest_pokemon_species(self, pokemon_id: int) -> Optional[Dict]:
        """
        Fetch pokemon species data (flavor text, generation, evolution chain).

        Args:
            pokemon_id: National Dex number

        Returns:
            Species dict or None
        """
        return self._fetch_from_api(f"pokemon-species/{pokemon_id}")

    @staticmethod
    def _clean_flavor_text(text: str) -> str:
        """
        Normalize raw flavor text.

        PokeAPI keeps the original game line breaks (\\n), page breaks (\\f) and
        soft hyphens, so the same sentence can appear with different whitespace.
        """
        text = text.replace("­\n", "").replace("­", "")
        return re.sub(r"\s+", " ", text).strip()

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

        for entry in species_data.get("flavor_text_entries", []):
            # Filter to English only
            if entry.get("language", {}).get("name") != "en":
                continue

            text = self._clean_flavor_text(entry.get("flavor_text", ""))

            # Skip duplicates (same text in different game versions)
            if text in seen_texts or not text:
                continue

            seen_texts.add(text)

            game_version = entry.get("version", {}).get("name", "unknown")
            entries.append({
                "flavor_text": text,
                "game_version": game_version,
                "generation": VERSION_TO_GENERATION.get(game_version, 0),
            })

        return entries

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
        poke_id = poke_detail.get("id")
        name = poke_detail.get("name")
        try:
            cursor = conn.cursor()

            # Insert main pokemon record
            national_dex = poke_species.get("id", poke_id)
            cursor.execute("""
                INSERT OR IGNORE INTO pokemon
                (id, national_dex_number, name, height_dm, weight_hg, base_experience, is_default)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                poke_id,
                national_dex,
                name,
                poke_detail.get("height"),
                poke_detail.get("weight"),
                poke_detail.get("base_experience"),
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

    def run_ingestion(self, num_pokemon: int = DEFAULT_NUM_POKEMON) -> None:
        """
        Run the full ingestion pipeline for National Dex #1 through #num_pokemon.

        Args:
            num_pokemon: How many pokemon to ingest (start small for testing)
        """
        print(f"\n{'='*60}")
        print(f"PokeAgent Data Ingestion (#1-#{num_pokemon})")
        print(f"{'='*60}\n")

        start = time.time()
        conn = self._init_database()
        failures = 0

        for poke_id in range(1, num_pokemon + 1):
            print(f"[{poke_id}/{num_pokemon}]", end=" ")

            poke_detail = self.ingest_pokemon_detail(poke_id)
            if not poke_detail:
                print("❌ (detail fetch failed)")
                failures += 1
                continue

            # Fetch species view (for flavor text)
            poke_species = self.ingest_pokemon_species(poke_id)
            if not poke_species:
                print(f"{poke_detail['name']} ❌ (species fetch failed)")
                failures += 1
                continue

            if self.insert_pokemon_to_db(poke_detail, poke_species, conn):
                flavor_count = len(self.extract_flavor_text_entries(poke_species))
                print(f"{poke_detail['name']} ✓ ({flavor_count} flavor texts)")
            else:
                failures += 1

        conn.close()
        print(f"\n{'='*60}")
        print(f"✓ Ingestion complete in {time.time() - start:.0f}s ({failures} failures)")
        print(f"{'='*60}\n")


def main() -> None:
    """Entry point for data ingestion."""
    parser = argparse.ArgumentParser(description="Ingest Pokemon data from PokeAPI")
    parser.add_argument(
        "--limit", type=int, default=DEFAULT_NUM_POKEMON,
        help="Ingest National Dex #1 through #LIMIT (default: 151, max: 1025)",
    )
    args = parser.parse_args()

    ingestor = PokemonDataIngestor(db_path=SQLITE_DB_PATH)
    ingestor.run_ingestion(num_pokemon=args.limit)


if __name__ == "__main__":
    main()
