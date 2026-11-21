import React from 'react';

/**
 * PokemonCard
 * -----------
 * Displays a Pokemon's sprite, types and BST.
 *
 * Props:
 *   pokemon: output of the pokemon_stats tool
 *            ({ name, national_dex_number, types, bst, ... })
 *
 * The sprite URL is the same one PokeAPI returns as sprites.front_default,
 * so no extra API request is needed.
 */
const SPRITE_URL = 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon';

export default function PokemonCard({ pokemon }) {
  return (
    <div className="inline-flex flex-col items-center bg-poke-cream border-2 border-poke-cream-dark
                    rounded-xl p-3 shadow-sm w-32 text-center">
      <img
        src={`${SPRITE_URL}/${pokemon.national_dex_number}.png`}
        alt={pokemon.name}
        className="w-20 h-20 object-contain"
        style={{ imageRendering: 'pixelated' }}
      />
      <p className="font-pixel text-xs text-poke-red-dark capitalize mt-1 leading-tight">
        {pokemon.name}
      </p>
      <div className="flex gap-1 mt-2 flex-wrap justify-center">
        {pokemon.types.map(t => (
          <span
            key={t}
            className="text-xs bg-poke-red text-white rounded-full px-2 py-0.5 capitalize"
          >
            {t}
          </span>
        ))}
      </div>
      <p className="text-xs text-gray-400 mt-1">BST {pokemon.bst}</p>
    </div>
  );
}
