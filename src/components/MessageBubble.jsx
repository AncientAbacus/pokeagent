import React from 'react';
import ReasoningTrace from './ReasoningTrace';
import PokemonCard from './PokemonCard';

/**
 * MessageBubble
 * -------------
 * Renders a single chat turn.
 *
 * User messages: right-aligned, red background
 * Assistant messages: left-aligned, cream background, with a card per Pokemon
 * the agent looked up and an optional ReasoningTrace
 */
export default function MessageBubble({ message }) {
  const isUser = message.role === 'user';
  const toolCalls = message.toolCalls || [];
  const pokemon = toolCalls
    .filter(c => c.tool === 'pokemon_stats' && c.output?.name)
    .map(c => c.output)
    .filter((p, i, all) => all.findIndex(q => q.name === p.name) === i);

  return (
    <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
      {/* Role label */}
      <span className="text-xs text-gray-400 mb-1 px-1">
        {isUser ? 'You' : 'PokeAgent'}
      </span>

      {/* Bubble */}
      <div
        className={`max-w-[80%] px-4 py-3 rounded-2xl text-sm leading-relaxed shadow-sm whitespace-pre-wrap
          ${isUser
            ? 'bg-poke-red text-white rounded-br-none'
            : 'bg-poke-cream border border-poke-cream-dark text-gray-800 rounded-bl-none'
          }`}
      >
        {message.content}
      </div>

      {pokemon.length > 0 && (
        <div className="mt-2 flex gap-2 flex-wrap">
          {pokemon.map(p => <PokemonCard key={p.name} pokemon={p} />)}
        </div>
      )}

      {/* Show reasoning trace below assistant messages if tools were used */}
      {!isUser && toolCalls.length > 0 && (
        <div className="mt-2 w-full max-w-[90%]">
          <ReasoningTrace toolCalls={toolCalls} />
        </div>
      )}
    </div>
  );
}
