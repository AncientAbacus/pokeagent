import React, { useState, useEffect } from 'react';
import axios from 'axios';

/**
 * PokemonCard
 * -----------
 * Fetches and displays a Pokemon's sprite + basic stats from the PokeAPI.
 * Used to add a visual element when the user asks about a specific Pokemon.
 *
 * Props:
 *   name: string — Pokemon name (lowercase, e.g. "pikachu")
 *
 * How it works:
 *   1. On mount, calls PokeAPI /pokemon/{name} to get the sprite URL
 *   2. Shows a loading skeleton while fetching
 *   3. Renders sprite + type badges when ready
 *
 * This is a "dumb" component — it only displays data, no business logic.
 */
export default function PokemonCard({ name }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!name) return;
    setLoading(true);
    setError(false);

    axios
      .get(`https://pokeapi.co/api/v2/pokemon/${name.toLowerCase()}`)
      .then(res => {
        setData({
          name: res.data.name,
          sprite: res.data.sprites.front_default,
          types: res.data.types.map(t => t.type.name),
          bst: res.data.stats.reduce((sum, s) => sum + s.base_stat, 0),
        });
        setLoading(false);
      })
      .catch(() => {
        setError(true);
        setLoading(false);
      });
  }, [name]);

  if (error) return null;

  return (
    <div className="inline-flex flex-col items-center bg-poke-cream border-2 border-poke-cream-dark
                    rounded-xl p-3 shadow-sm w-32 text-center">
      {loading ? (
        <>
          <div className="w-20 h-20 bg-poke-cream-dark rounded-lg animate-pulse" />
          <div className="mt-2 h-3 w-16 bg-poke-cream-dark rounded animate-pulse" />
        </>
      ) : (
        <>
          {data?.sprite && (
            <img
              src={data.sprite}
              alt={data.name}
              className="w-20 h-20 object-contain"
              style={{ imageRendering: 'pixelated' }}
            />
          )}
          <p className="font-pixel text-xs text-poke-red-dark capitalize mt-1 leading-tight">
            {data?.name}
          </p>
          <div className="flex gap-1 mt-2 flex-wrap justify-center">
            {data?.types.map(t => (
              <span
                key={t}
                className="text-xs bg-poke-red text-white rounded-full px-2 py-0.5 capitalize"
              >
                {t}
              </span>
            ))}
          </div>
          <p className="text-xs text-gray-400 mt-1">BST {data?.bst}</p>
        </>
      )}
    </div>
  );
}
