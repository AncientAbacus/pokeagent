import React from 'react';
import ReasoningTrace from './ReasoningTrace';

/**
 * MessageBubble
 * -------------
 * Renders a single chat turn.
 *
 * User messages: right-aligned, red background
 * Assistant messages: left-aligned, cream background, with optional ReasoningTrace
 */
export default function MessageBubble({ message }) {
  const isUser = message.role === 'user';

  return (
    <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
      {/* Role label */}
      <span className="text-xs text-gray-400 mb-1 px-1">
        {isUser ? 'You' : 'PokeAgent'}
      </span>

      {/* Bubble */}
      <div
        className={`max-w-[80%] px-4 py-3 rounded-2xl text-sm leading-relaxed shadow-sm
          ${isUser
            ? 'bg-poke-red text-white rounded-br-none'
            : 'bg-poke-cream border border-poke-cream-dark text-gray-800 rounded-bl-none'
          }`}
      >
        {/* Preserve line breaks in the answer */}
        {message.content.split('\n').map((line, i) => (
          <span key={i}>
            {line}
            {i < message.content.split('\n').length - 1 && <br />}
          </span>
        ))}
      </div>

      {/* Show reasoning trace below assistant messages if tools were used */}
      {!isUser && message.toolCalls && message.toolCalls.length > 0 && (
        <div className="mt-2 w-full max-w-[90%]">
          <ReasoningTrace toolCalls={message.toolCalls} />
        </div>
      )}
    </div>
  );
}
