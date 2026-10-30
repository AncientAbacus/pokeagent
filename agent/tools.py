"""
Agent Tools for PokeAgent
=========================

Each tool is a pure function that:
- Takes clear inputs (type-hinted)
- Returns structured outputs
- Is independently testable
- Logs reasoning steps for agent transparency

Import these into agent.py to wire them into LangGraph.
"""

import sqlite3
import logging
from typing import List, Dict, Optional, Any
import os

# Logging for transparency
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "./data/pokeagent.db")


# ============================================================================
# TOOL 1: Get Pokemon Stats
# ============================================================================

def get_pokemon_stats(pokemon_name: str) -> Optional[Dict[str, Any]]:
    """
    Get detailed stats for a Pokemon.
    
    Args:
        pokemon_name: Pokemon name (case-insensitive)
        
    Returns:
        Dict with hp, attack, defense, sp_atk, sp_def, speed, bst
        or None if Pokemon not found
        
    Example:
        >>> get_pokemon_stats("pikachu")
        {
            'name': 'pikachu',
            'hp': 35, 'attack': 55, 'defense': 40,
            'sp_atk': 50, 'sp_def': 50, 'speed': 90,
            'bst': 320,
            'types': ['electric'],
            'abilities': ['static', 'lightning-rod']
        }
    """
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get Pokemon
    cursor.execute("""
        SELECT p.id, p.name, p.national_dex_number,
               ps.hp, ps.attack, ps.defense, ps.sp_atk, ps.sp_def, ps.speed, ps.bst
        FROM pokemon p
        LEFT JOIN pokemon_stats ps ON p.id = ps.pokemon_id
        WHERE LOWER(p.name) = LOWER(?)
        LIMIT 1
    """, (pokemon_name,))
    
    poke_row = cursor.fetchone()
    if not poke_row:
        conn.close()
        logger.warning(f"Pokemon not found: {pokemon_name}")
        return None
    
    poke_id = poke_row['id']
    
    # Get types
    cursor.execute("""
        SELECT type_name FROM pokemon_types
        WHERE pokemon_id = ?
        ORDER BY slot
    """, (poke_id,))
    types = [row['type_name'] for row in cursor.fetchall()]
    
    # Get abilities
    cursor.execute("""
        SELECT ability_name FROM pokemon_abilities
        WHERE pokemon_id = ?
        ORDER BY (CASE WHEN is_hidden THEN 1 ELSE 0 END)
    """, (poke_id,))
    abilities = [row['ability_name'] for row in cursor.fetchall()]
    
    conn.close()
    
    result = {
        'name': poke_row['name'],
        'national_dex_number': poke_row['national_dex_number'],
        'hp': poke_row['hp'],
        'attack': poke_row['attack'],
        'defense': poke_row['defense'],
        'sp_atk': poke_row['sp_atk'],
        'sp_def': poke_row['sp_def'],
        'speed': poke_row['speed'],
        'bst': poke_row['bst'],  # Base Stat Total
        'types': types,
        'abilities': abilities
    }
    
    logger.info(f"Retrieved stats for {pokemon_name}: BST={result['bst']}")
    return result


# ============================================================================
# TOOL 2: Search by Criteria
# ============================================================================

def search_by_criteria(
    type_filter: Optional[str] = None,
    min_bst: Optional[int] = None,
    max_bst: Optional[int] = None,
    move: Optional[str] = None,
    ability: Optional[str] = None,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Find Pokemon matching criteria (type, BST range, move, ability).
    
    Args:
        type_filter: Filter to specific type (e.g., "water", "electric")
        min_bst: Minimum base stat total
        max_bst: Maximum base stat total
        move: Pokemon that can learn this move
        ability: Pokemon with this ability
        limit: Max results to return
        
    Returns:
        List of Pokemon with stats
        
    Example:
        >>> search_by_criteria(type_filter="water", min_bst=400)
        # Returns all Water types with BST >= 400
    """
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Build query dynamically based on filters
    query = """
        SELECT DISTINCT p.id, p.name, ps.bst
        FROM pokemon p
        LEFT JOIN pokemon_stats ps ON p.id = ps.pokemon_id
        WHERE 1=1
    """
    params = []
    
    if type_filter:
        query += """
            AND p.id IN (
                SELECT pokemon_id FROM pokemon_types 
                WHERE LOWER(type_name) = LOWER(?)
            )
        """
        params.append(type_filter)
    
    if min_bst is not None:
        query += " AND ps.bst >= ?"
        params.append(min_bst)
    
    if max_bst is not None:
        query += " AND ps.bst <= ?"
        params.append(max_bst)
    
    if move:
        query += """
            AND p.id IN (
                SELECT pokemon_id FROM pokemon_moves
                WHERE LOWER(move_name) = LOWER(?)
            )
        """
        params.append(move)
    
    if ability:
        query += """
            AND p.id IN (
                SELECT pokemon_id FROM pokemon_abilities
                WHERE LOWER(ability_name) = LOWER(?)
            )
        """
        params.append(ability)
    
    query += f" ORDER BY ps.bst DESC LIMIT {limit}"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    results = [
        {'name': row['name'], 'bst': row['bst']}
        for row in rows
    ]
    
    filter_desc = []
    if type_filter:
        filter_desc.append(f"type={type_filter}")
    if min_bst is not None or max_bst is not None:
        bst_range = f"{min_bst or '?'}-{max_bst or '?'}"
        filter_desc.append(f"bst={bst_range}")
    if move:
        filter_desc.append(f"move={move}")
    if ability:
        filter_desc.append(f"ability={ability}")
    
    filter_str = ", ".join(filter_desc) if filter_desc else "no filters"
    logger.info(f"Search completed ({filter_str}): found {len(results)} Pokemon")
    
    return results


# ============================================================================
# TOOL 3: Type Matchups
# ============================================================================

# 18x18 type effectiveness table (generation 9)
# Rows = attacker type, Columns = defender type
# Value: 1.0 = neutral, 2.0 = super effective, 0.5 = not very effective
TYPE_MATCHUPS = {
    # Format: attacking_type -> {defending_type: effectiveness}
    "normal": {"rock": 0.5, "steel": 0.5, "ghost": 0},
    "fire": {"fire": 0.5, "water": 0.5, "grass": 2, "ice": 2, "bug": 2, "steel": 2, "fairy": 1},
    "water": {"fire": 2, "water": 0.5, "grass": 0.5, "ground": 2},
    "electric": {"water": 2, "electric": 0.5, "grass": 0.5, "ground": 0, "flying": 2},
    "grass": {"fire": 0.5, "water": 2, "grass": 0.5, "poison": 0.5, "ground": 2, "flying": 0.5, "bug": 0.5, "steel": 0.5, "fairy": 0.5},
    "ice": {"fire": 0.5, "water": 0.5, "grass": 2, "ice": 0.5, "ground": 2, "flying": 2, "dragon": 2},
    "fighting": {"normal": 2, "flying": 0.5, "poison": 0.5, "rock": 2, "bug": 0.5, "ghost": 0, "steel": 2, "psychic": 0.5, "ice": 2, "dark": 2, "fairy": 0.5},
    "poison": {"grass": 2, "poison": 0.5, "ground": 0, "rock": 0.5, "bug": 1, "ghost": 0.5, "steel": 0, "fairy": 2},
    "ground": {"fire": 2, "electric": 2, "grass": 0.5, "poison": 2, "flying": 0, "bug": 0.5, "rock": 2, "steel": 2},
    "flying": {"normal": 1, "fighting": 2, "flying": 1, "poison": 1, "ground": 1, "bug": 2, "rock": 0.5, "steel": 0.5, "grass": 2, "electric": 0.5, "psychic": 1},
    "psychic": {"fighting": 2, "poison": 2, "psychic": 0.5, "dark": 0, "steel": 0.5},
    "bug": {"fire": 0.5, "grass": 2, "fighting": 0.5, "poison": 0.5, "flying": 0.5, "psychic": 2, "ghost": 0.5, "dark": 2, "steel": 0.5, "fairy": 0.5},
    "rock": {"normal": 1, "fire": 2, "water": 0.5, "grass": 0.5, "ice": 2, "fighting": 0.5, "ground": 0.5, "flying": 2, "bug": 2, "steel": 0.5},
    "ghost": {"normal": 0, "fighting": 1, "poison": 1, "bug": 1, "ghost": 2, "dark": 0.5, "steel": 1, "fairy": 1},
    "dragon": {"dragon": 2, "steel": 0.5, "fairy": 0},
    "dark": {"fighting": 0.5, "ghost": 2, "dark": 0.5, "steel": 0.5, "fairy": 0.5},
    "steel": {"normal": 2, "flying": 2, "rock": 2, "bug": 1, "steel": 0.5, "grass": 1, "ice": 2, "dragon": 1, "fairy": 2, "fire": 0.5, "water": 0.5, "psychic": 1, "poison": 2, "ground": 1},
    "fairy": {"fighting": 2, "poison": 0.5, "bug": 1, "dark": 2, "steel": 0.5, "fire": 0.5}
}


def get_type_matchups(
    pokemon_type: str,
    matchup_direction: str = "resistant_to"
) -> Dict[str, List[str]]:
    """
    Get type advantages/disadvantages for a given type.
    
    Args:
        pokemon_type: Type name (e.g., "water", "fire")
        matchup_direction: 
            - "super_effective_against": What does this type beat?
            - "resistant_to": What's not very effective against this type?
            - "weak_to": What beats this type?
            
    Returns:
        Dict with lists of types
        
    Example:
        >>> get_type_matchups("water", "weak_to")
        {
            'weak_to': ['electric', 'grass'],
            'super_effective_against': ['fire', 'ground', 'rock'],
            'resists': ['water', 'ice', 'steel']
        }
    """
    ptype = pokemon_type.lower()
    
    if ptype not in TYPE_MATCHUPS:
        logger.error(f"Unknown type: {ptype}")
        return {"error": f"Unknown type: {ptype}"}
    
    result = {}
    
    # Super effective against (what this type beats)
    super_effective = [
        def_type for def_type, mult in TYPE_MATCHUPS[ptype].items()
        if mult == 2.0
    ]
    result['super_effective_against'] = sorted(super_effective)
    
    # Resists (what's not very effective against this type)
    resists = [
        atk_type for atk_type, matchups in TYPE_MATCHUPS.items()
        if matchups.get(ptype, 1.0) == 0.5
    ]
    result['resists'] = sorted(resists)
    
    # Weak to (what beats this type)
    weak_to = [
        atk_type for atk_type, matchups in TYPE_MATCHUPS.items()
        if matchups.get(ptype, 1.0) == 2.0
    ]
    result['weak_to'] = sorted(weak_to)
    
    # Immune to (what can't touch this type)
    immune_to = [
        atk_type for atk_type, matchups in TYPE_MATCHUPS.items()
        if matchups.get(ptype, 1.0) == 0
    ]
    result['immune_to'] = sorted(immune_to)
    
    logger.info(f"Type matchups for {ptype}: weak={result['weak_to']}, resists={result['resists']}")
    return result


# ============================================================================
# TOOL 4: Retrieve Lore (RAG)
# ============================================================================

def retrieve_lore(query: str, k: int = 5, pokemon_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Retrieve Pokemon lore/flavor text via semantic search.
    
    Requires embedder.py to have already populated ChromaDB.
    
    Args:
        query: Natural language query (e.g., "origins of legendary Pokemon")
        k: Number of results
        pokemon_filter: Optionally limit to one Pokemon's lore
        
    Returns:
        List of {pokemon_name, flavor_text, game_version, generation, distance}
        
    Example:
        >>> retrieve_lore("What makes Cubone sad?", k=3)
        [
            {
                'pokemon_name': 'cubone',
                'flavor_text': '...',
                'generation': 1,
                'game_version': 'red',
                'distance': 0.234
            },
            ...
        ]
    """
    # Shared singleton so the embedding model loads once, not per call
    from rag.retriever import retrieve
    
    try:
        results = retrieve(query, k=k, pokemon_filter=pokemon_filter)
        logger.info(f"RAG retrieval for '{query}': found {len(results)} entries")
        return results
    except Exception as e:
        logger.error(f"Error retrieving lore: {e}")
        return [{"error": str(e)}]


# ============================================================================
# TOOL 5: Suggest Counter Team (Multi-step)
# ============================================================================

def suggest_counter_team(
    target_pokemon: str,
    team_size: int = 3,
    max_bst: Optional[int] = 700
) -> Dict[str, Any]:
    """
    Suggest a team of Pokemon to counter a target Pokemon.
    
    This tool uses other tools (get_pokemon_stats, get_type_matchups, search_by_criteria).
    
    Args:
        target_pokemon: Pokemon name to counter
        team_size: How many Pokemon to recommend
        max_bst: Optional cap on BST for balance
        
    Returns:
        Dict with reasoning and recommended Pokemon
        
    Example:
        >>> suggest_counter_team("garchomp")
        {
            'target': 'garchomp',
            'target_types': ['dragon', 'ground'],
            'recommended_team': [
                {'name': 'salamence', 'reason': 'ice weakness'},
                ...
            ],
            'reasoning': "..."
        }
    """
    logging.info(f"Building counter team for {target_pokemon}")
    
    # Step 1: Get target stats & types
    target_stats = get_pokemon_stats(target_pokemon)
    if not target_stats:
        return {"error": f"Pokemon not found: {target_pokemon}"}
    
    target_types = target_stats['types']
    logging.info(f"  Target types: {target_types}")
    
    # Step 2: Identify weaknesses
    weak_to_types = set()
    for ptype in target_types:
        matchups = get_type_matchups(ptype)
        weak_to_types.update(matchups.get('weak_to', []))
    
    logging.info(f"  Weak to: {weak_to_types}")
    
    # Step 3: Search for strong counters in each weakness
    counters = []
    for weakness in list(weak_to_types)[:team_size]:
        candidates = search_by_criteria(
            type_filter=weakness,
            min_bst=500,
            max_bst=max_bst,
            limit=3
        )
        if candidates:
            counters.append({
                'name': candidates[0]['name'],
                'bst': candidates[0]['bst'],
                'reason': f"Has {weakness} moves, weak_to {weakness}"
            })
    
    return {
        'target': target_pokemon,
        'target_types': target_types,
        'recommended_team': counters[:team_size],
        'reasoning': f"Counters weak to {list(weak_to_types)[:team_size]}"
    }


if __name__ == "__main__":
    # Quick function tests
    print("\n" + "=" * 60)
    print("Tool Testing")
    print("=" * 60)
    
    # Test 1: Stats
    print("\n[Test 1] get_pokemon_stats('pikachu')")
    stats = get_pokemon_stats("pikachu")
    if stats:
        print(f"  ✓ Pikachu BST: {stats['bst']}, Types: {stats['types']}")
    
    # Test 2: Search
    print("\n[Test 2] search_by_criteria(type_filter='water', min_bst=400)")
    results = search_by_criteria(type_filter="water", min_bst=400)
    print(f"  ✓ Found {len(results)} Water types with BST >= 400")
    if results:
        print(f"    Top: {results[0]['name']} (BST {results[0]['bst']})")
    
    # Test 3: Type Matchups
    print("\n[Test 3] get_type_matchups('water')")
    matchups = get_type_matchups("water")
    print(f"  ✓ Water weak to: {matchups['weak_to']}")
    print(f"  ✓ Water super effective against: {matchups['super_effective_against']}")
    
    print("\n" + "=" * 60)
