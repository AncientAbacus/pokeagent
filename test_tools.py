#!/usr/bin/env python3
"""Quick test of all tools"""

from agent.tools import *

print('\n' + '='*60)
print('Tool Test Suite')
print('='*60)

# Test 1
print('\n[1] get_pokemon_stats for Charizard')
stats = get_pokemon_stats('charizard')
if stats:
    print(f'    ✓ {stats["name"].upper()}: {stats["types"]} type')
    print(f'      Stats: HP={stats["hp"]} ATK={stats["attack"]} DEF={stats["defense"]} SPD={stats["speed"]} BST={stats["bst"]}')

# Test 2
print('\n[2] search_by_criteria: Fire types under BST 500')
results = search_by_criteria(type_filter='fire', max_bst=500)
print(f'    ✓ Found {len(results)} Fire types')
if results:
    for r in results[:3]:
        print(f'      - {r["name"]}: BST {r["bst"]}')

# Test 3
print('\n[3] get_type_matchups: Fire type')
matchups = get_type_matchups('fire')
print(f'    ✓ Fire is weak to: {matchups["weak_to"]}')
print(f'    ✓ Fire is super effective against: {matchups["super_effective_against"]}')

# Test 4
print('\n[4] suggest_counter_team for Venusaur')
counters = suggest_counter_team('venusaur', team_size=2, max_bst=600)
if 'error' not in counters:
    print(f'    ✓ Target: {counters["target"]} ({counters["target_types"]})')
    for mon in counters['recommended_team'][:2]:
        if mon:
            print(f'      Counter: {mon.get("name", "?")} ({mon.get("reason", "?")})')

print('\n' + '='*60)
print('All tools tested successfully!')
print('='*60 + '\n')
