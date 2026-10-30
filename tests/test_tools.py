"""
Unit tests for agent tools.

Type-chart tests are pure Python. Counter-team tests need the SQLite DB built
by ``python -m data.ingest`` (Gen 1 or more) and are skipped if it is missing.
"""

import os

import pytest

from agent import tools
from agent.tools import (
    TYPE_MATCHUPS,
    get_combined_multiplier,
    get_weaknesses,
    suggest_counter_team,
)

requires_db = pytest.mark.skipif(
    not os.path.exists(tools.SQLITE_DB_PATH),
    reason=f"SQLite DB not found at {tools.SQLITE_DB_PATH}; run `python -m data.ingest`",
)


# ============================================================================
# Type chart
# ============================================================================

def test_type_chart_covers_all_18_types() -> None:
    """Every attacking and defending type in the chart is one of the 18 types."""
    assert len(TYPE_MATCHUPS) == 18
    for atk_type, row in TYPE_MATCHUPS.items():
        for def_type, mult in row.items():
            assert def_type in TYPE_MATCHUPS, f"{atk_type} -> unknown {def_type}"
            assert mult in (0, 0.5, 2), f"{atk_type} -> {def_type} = {mult}"


@pytest.mark.parametrize("atk, defenders, expected", [
    ("rock", ["fire", "flying"], 4.0),
    ("ice", ["dragon", "ground"], 4.0),
    ("bug", ["grass", "poison"], 1.0),
    ("poison", ["grass", "poison"], 1.0),
    ("ground", ["grass", "poison"], 1.0),
    ("fire", ["grass", "poison"], 2.0),
    ("electric", ["water", "ground"], 0.0),
    ("grass", ["fire", "flying"], 0.25),
    ("steel", ["grass", "poison"], 1.0),
])
def test_combined_multiplier(atk: str, defenders: list, expected: float) -> None:
    """Dual-type multipliers are the product of the per-type multipliers."""
    assert get_combined_multiplier(atk, defenders) == expected


def test_weaknesses_venusaur_typing() -> None:
    """Grass/poison is weak to exactly fire, flying, ice and psychic (2x each)."""
    assert get_weaknesses(["grass", "poison"]) == {
        "fire": 2.0, "flying": 2.0, "ice": 2.0, "psychic": 2.0,
    }


def test_weaknesses_4x_listed_first() -> None:
    """4x weaknesses come before 2x weaknesses."""
    weaknesses = get_weaknesses(["fire", "flying"])
    assert list(weaknesses) == ["rock", "electric", "water"]
    assert weaknesses["rock"] == 4.0


# ============================================================================
# suggest_counter_team (needs DB)
# ============================================================================

def _assert_team_is_valid(result: dict, target: str) -> None:
    """Shared checks: no target, no shared typing, no duplicates, real weakness."""
    assert "error" not in result
    team = result["recommended_team"]
    target_types = set(result["target_types"])
    names = [m["name"] for m in team]

    assert target not in names
    assert len(names) == len(set(names))
    for member in team:
        assert set(member["types"]) != target_types
        assert member["counter_type"] in member["types"]
        assert get_combined_multiplier(member["counter_type"], result["target_types"]) >= 2
        assert member["multiplier"] >= 2


@requires_db
def test_counter_team_venusaur() -> None:
    """Venusaur counters are fire/ice/flying/psychic types, never bug/poison or itself."""
    result = suggest_counter_team("venusaur", team_size=4, max_bst=600)
    _assert_team_is_valid(result, "venusaur")

    assert set(result["weaknesses"]) == {"fire", "flying", "ice", "psychic"}
    team = result["recommended_team"]
    assert len(team) == 4
    assert {m["counter_type"] for m in team} == {"fire", "flying", "ice", "psychic"}
    for member in team:
        assert member["reason"] == (
            f"{member['counter_type']}-type, {member['counter_type']} is 2x vs grass/poison"
        )
        assert "bug" not in member["reason"] and "poison-type" not in member["reason"]


@requires_db
def test_counter_team_charizard_prefers_4x_rock() -> None:
    """Charizard's 4x rock weakness is used for the first pick."""
    result = suggest_counter_team("charizard", team_size=3, max_bst=600)
    _assert_team_is_valid(result, "charizard")

    assert result["weaknesses"]["rock"] == 4.0
    first = result["recommended_team"][0]
    assert first["counter_type"] == "rock"
    assert "rock" in first["types"]
    assert first["reason"] == "rock-type, rock is 4x vs fire/flying"


@requires_db
def test_counter_team_fills_slots_without_duplicates() -> None:
    """More slots than weaknesses cycles weaknesses without repeating a Pokemon."""
    result = suggest_counter_team("charizard", team_size=6, max_bst=600)
    _assert_team_is_valid(result, "charizard")
    assert len(result["recommended_team"]) == 6


@requires_db
def test_counter_team_unknown_pokemon() -> None:
    """Unknown names return an error instead of raising."""
    assert "error" in suggest_counter_team("notapokemon")
