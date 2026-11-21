"""Unit tests for agent/tools.py. DB-backed tests need `python -m data.ingest` first."""

from pathlib import Path

import pytest

from agent.tools import (
    SQLITE_DB_PATH,
    TYPE_MATCHUPS,
    damage_multiplier,
    get_type_matchups,
    suggest_counter_team,
)

needs_db = pytest.mark.skipif(not Path(SQLITE_DB_PATH).exists(), reason="run python -m data.ingest first")


def test_type_chart_matches_official_totals() -> None:
    """The Gen 6+ chart has exactly 51 super-effective, 61 resisted and 8 immune pairs."""
    values = [v for row in TYPE_MATCHUPS.values() for v in row.values()]
    assert len(TYPE_MATCHUPS) == 18
    assert (values.count(2), values.count(0.5), values.count(0)) == (51, 61, 8)


@pytest.mark.parametrize("ptype, key, expected", [
    ("dragon", "weak_to", ["dragon", "fairy", "ice"]),
    ("normal", "weak_to", ["fighting"]),
    ("psychic", "weak_to", ["bug", "dark", "ghost"]),
    ("ground", "immune_to", ["electric"]),
    ("steel", "immune_to", ["poison"]),
    ("water", "super_effective_against", ["fire", "ground", "rock"]),
])
def test_known_matchups(ptype: str, key: str, expected: list) -> None:
    """Spot-check matchups that the old chart got wrong."""
    assert get_type_matchups(ptype)[key] == expected


def test_dual_type_multiplier() -> None:
    """Dual types multiply: rock is 4x on Charizard, bug is neutral on Venusaur."""
    assert damage_multiplier("rock", ["fire", "flying"]) == 4
    assert damage_multiplier("bug", ["grass", "poison"]) == 1
    assert damage_multiplier("ground", ["electric", "flying"]) == 0


@needs_db
def test_counter_team_only_super_effective() -> None:
    """Every counter for Venusaur hits it super effectively and is not Venusaur."""
    team = suggest_counter_team("venusaur")["recommended_team"]
    assert len(team) == 3
    names = [c["name"] for c in team]
    assert "venusaur" not in names and len(set(names)) == 3
    for c in team:
        assert c["reason"].split("-type")[0] in {"fire", "ice", "flying", "psychic"}
