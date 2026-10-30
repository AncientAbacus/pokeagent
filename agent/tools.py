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
from typing import List, Dict, Optional, Any, Set
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

# 18x18 type effectiveness table (generation 6+)
# Rows = attacker type, Columns = defender type
# Value: 2 = super effective, 0.5 = not very effective, 0 = no effect.
# Pairs not listed are neutral (1.0).
TYPE_MATCHUPS = {
    # Format: attacking_type -> {defending_type: effectiveness}
    "normal": {"rock": 0.5, "ghost": 0, "steel": 0.5},
    "fire": {"fire": 0.5, "water": 0.5, "grass": 2, "ice": 2, "bug": 2, "rock": 0.5, "dragon": 0.5, "steel": 2},
    "water": {"fire": 2, "water": 0.5, "grass": 0.5, "ground": 2, "rock": 2, "dragon": 0.5},
    "electric": {"water": 2, "electric": 0.5, "grass": 0.5, "ground": 0, "flying": 2, "dragon": 0.5},
    "grass": {"fire": 0.5, "water": 2, "grass": 0.5, "poison": 0.5, "ground": 2, "flying": 0.5, "bug": 0.5, "rock": 2, "dragon": 0.5, "steel": 0.5},
    "ice": {"fire": 0.5, "water": 0.5, "grass": 2, "ice": 0.5, "ground": 2, "flying": 2, "dragon": 2, "steel": 0.5},
    "fighting": {"normal": 2, "ice": 2, "poison": 0.5, "flying": 0.5, "psychic": 0.5, "bug": 0.5, "rock": 2, "ghost": 0, "dark": 2, "steel": 2, "fairy": 0.5},
    "poison": {"grass": 2, "poison": 0.5, "ground": 0.5, "rock": 0.5, "ghost": 0.5, "steel": 0, "fairy": 2},
    "ground": {"fire": 2, "electric": 2, "grass": 0.5, "poison": 2, "flying": 0, "bug": 0.5, "rock": 2, "steel": 2},
    "flying": {"electric": 0.5, "grass": 2, "fighting": 2, "bug": 2, "rock": 0.5, "steel": 0.5},
    "psychic": {"fighting": 2, "poison": 2, "psychic": 0.5, "dark": 0, "steel": 0.5},
    "bug": {"fire": 0.5, "grass": 2, "fighting": 0.5, "poison": 0.5, "flying": 0.5, "psychic": 2, "ghost": 0.5, "dark": 2, "steel": 0.5, "fairy": 0.5},
    "rock": {"fire": 2, "ice": 2, "fighting": 0.5, "ground": 0.5, "flying": 2, "bug": 2, "steel": 0.5},
    "ghost": {"normal": 0, "psychic": 2, "ghost": 2, "dark": 0.5},
    "dragon": {"dragon": 2, "steel": 0.5, "fairy": 0},
    "dark": {"fighting": 0.5, "psychic": 2, "ghost": 2, "dark": 0.5, "fairy": 0.5},
    "steel": {"fire": 0.5, "water": 0.5, "electric": 0.5, "ice": 2, "rock": 2, "steel": 0.5, "fairy": 2},
    "fairy": {"fire": 0.5, "fighting": 2, "poison": 0.5, "dragon": 2, "dark": 2, "steel": 0.5},
}


def get_combined_multiplier(attacking_type: str, defending_types: List[str]) -> float:
    """
    Compute the damage multiplier of one attacking type against a (possibly dual) typing.

    Per-type multipliers are multiplied together, so dual-type interactions
    (4x, 0.25x, or a weakness cancelled by a resistance) are handled correctly.

    Args:
        attacking_type: Attacking move type (e.g., "rock")
        defending_types: The defender's types (e.g., ["fire", "flying"])

    Returns:
        Combined multiplier (0, 0.25, 0.5, 1, 2, or 4)

    Example:
        >>> get_combined_multiplier("rock", ["fire", "flying"])
        4.0
    """
    chart = TYPE_MATCHUPS.get(attacking_type.lower(), {})
    multiplier = 1.0
    for def_type in defending_types:
        multiplier *= chart.get(def_type.lower(), 1.0)
    return multiplier


def get_weaknesses(defending_types: List[str]) -> Dict[str, float]:
    """
    List every attacking type that is super effective against a typing.

    Args:
        defending_types: The defender's types (e.g., ["grass", "poison"])

    Returns:
        Dict of attacking_type -> multiplier (>= 2), ordered strongest first
        (4x before 2x), then alphabetically

    Example:
        >>> get_weaknesses(["fire", "flying"])
        {'rock': 4.0, 'electric': 2.0, 'water': 2.0}
    """
    weaknesses = {
        atk_type: get_combined_multiplier(atk_type, defending_types)
        for atk_type in TYPE_MATCHUPS
    }
    ordered = sorted(
        ((t, m) for t, m in weaknesses.items() if m >= 2),
        key=lambda item: (-item[1], item[0]),
    )
    return dict(ordered)


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
    from rag.embedder import PokemonEmbedder
    
    try:
        embedder = PokemonEmbedder()
        results = embedder.search(query, k=k, pokemon_filter=pokemon_filter)
        logger.info(f"RAG retrieval for '{query}': found {len(results)} entries")
        return results
    except Exception as e:
        logger.error(f"Error retrieving lore: {e}")
        return [{"error": str(e)}]


# ============================================================================
# TOOL 5: Suggest Counter Team (Multi-step)
# ============================================================================

def _get_types_for_pokemon(names: List[str]) -> Dict[str, List[str]]:
    """
    Look up the types of several Pokemon in one query.

    Args:
        names: Pokemon names (case-insensitive)

    Returns:
        Dict of lowercase name -> list of types ordered by slot
    """
    if not names:
        return {}
    conn = sqlite3.connect(SQLITE_DB_PATH)
    placeholders = ",".join("?" for _ in names)
    rows = conn.execute(f"""
        SELECT LOWER(p.name), pt.type_name
        FROM pokemon p
        JOIN pokemon_types pt ON p.id = pt.pokemon_id
        WHERE LOWER(p.name) IN ({placeholders})
        ORDER BY p.name, pt.slot
    """, [n.lower() for n in names]).fetchall()
    conn.close()

    types_by_name: Dict[str, List[str]] = {}
    for name, type_name in rows:
        types_by_name.setdefault(name, []).append(type_name)
    return types_by_name


def _format_multiplier(multiplier: float) -> str:
    """Format a multiplier like 4.0 -> '4x' or 0.5 -> '0.5x'."""
    return f"{multiplier:g}x"


def suggest_counter_team(
    target_pokemon: str,
    team_size: int = 3,
    max_bst: Optional[int] = 700,
    candidates_per_type: int = 10
) -> Dict[str, Any]:
    """
    Suggest a team of Pokemon to counter a target Pokemon.

    Weaknesses are computed against the target's full typing (per-type
    multipliers are multiplied), so only types that are truly super effective
    (>= 2x) are used, with 4x weaknesses tried first. For each weakness the
    highest-BST Pokemon of that type is picked, skipping the target itself,
    anything sharing the target's exact typing, and Pokemon already chosen.
    If there are fewer weaknesses than team slots, weaknesses are cycled
    again to pick the next-best candidate for each.

    Recommendations are based on the counter's own type (STAB), not a verified
    movepool.

    Args:
        target_pokemon: Pokemon name to counter
        team_size: How many Pokemon to recommend
        max_bst: Optional cap on BST for balance
        candidates_per_type: How many top-BST Pokemon to consider per weakness

    Returns:
        Dict with target info, weaknesses, recommended Pokemon and reasoning

    Example:
        >>> suggest_counter_team("charizard")
        {
            'target': 'charizard',
            'target_types': ['fire', 'flying'],
            'weaknesses': {'rock': 4.0, 'electric': 2.0, 'water': 2.0},
            'recommended_team': [
                {'name': 'aerodactyl', 'bst': 515, 'types': ['rock', 'flying'],
                 'counter_type': 'rock', 'multiplier': 4.0,
                 'reason': 'rock-type, rock is 4x vs fire/flying'},
                ...
            ],
            'reasoning': "..."
        }
    """
    logger.info(f"Building counter team for {target_pokemon}")

    # Step 1: Get target stats & types
    target_stats = get_pokemon_stats(target_pokemon)
    if not target_stats:
        return {"error": f"Pokemon not found: {target_pokemon}"}

    target_name = target_stats['name'].lower()
    target_types = target_stats['types']
    target_typing = "/".join(target_types)
    logger.info(f"  Target types: {target_types}")

    # Step 2: Combined weaknesses against the full typing (4x first)
    weaknesses = get_weaknesses(target_types)
    logger.info(f"  Weaknesses: {weaknesses}")

    if not weaknesses:
        return {
            'target': target_name,
            'target_types': target_types,
            'weaknesses': {},
            'recommended_team': [],
            'reasoning': f"{target_name} ({target_typing}) has no super effective weaknesses",
        }

    # Step 3: Gather eligible candidates for each weakness, best BST first
    candidates_by_type: Dict[str, List[Dict[str, Any]]] = {}
    for weakness in weaknesses:
        results = search_by_criteria(
            type_filter=weakness,
            max_bst=max_bst,
            limit=candidates_per_type
        )
        types_by_name = _get_types_for_pokemon([r['name'] for r in results])
        eligible = []
        for r in results:
            name = r['name'].lower()
            cand_types = types_by_name.get(name, [])
            if name == target_name or set(cand_types) == set(target_types):
                continue
            eligible.append({**r, 'types': cand_types})
        candidates_by_type[weakness] = eligible

    # Step 4: Round-robin over weaknesses (strongest first), no duplicates
    team: List[Dict[str, Any]] = []
    chosen: Set[str] = set()
    while len(team) < team_size:
        added = False
        for weakness, multiplier in weaknesses.items():
            if len(team) >= team_size:
                break
            pool = candidates_by_type[weakness]
            while pool and pool[0]['name'].lower() in chosen:
                pool.pop(0)
            if not pool:
                continue
            pick = pool.pop(0)
            chosen.add(pick['name'].lower())
            team.append({
                'name': pick['name'],
                'bst': pick['bst'],
                'types': pick['types'],
                'counter_type': weakness,
                'multiplier': multiplier,
                'reason': (
                    f"{weakness}-type, {weakness} is "
                    f"{_format_multiplier(multiplier)} vs {target_typing}"
                ),
            })
            added = True
        if not added:
            break

    weakness_desc = ", ".join(
        f"{t} ({_format_multiplier(m)})" for t, m in weaknesses.items()
    )
    logger.info(f"  Recommended: {[m['name'] for m in team]}")
    return {
        'target': target_name,
        'target_types': target_types,
        'weaknesses': weaknesses,
        'recommended_team': team,
        'reasoning': (
            f"{target_name} ({target_typing}) is weak to {weakness_desc}. "
            f"Picked the highest-BST Pokemon of each weakness type, strongest "
            f"weakness first, excluding the target and its own typing."
        ),
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
