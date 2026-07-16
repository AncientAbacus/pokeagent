import React, { useEffect, useRef, useState } from 'react';
import MessageBubble from './MessageBubble';

/**
 * ChatWindow
 * ----------
 * Renders the scrollable message list + the text input bar.
 *
 * Key patterns to know:
 * - useRef on the scroll container lets us auto-scroll to bottom after updates
 * - useEffect with [messages] dependency fires whenever a new message arrives
 * - Controlled input: value comes from state, onChange updates state
 */
export default function ChatWindow({ messages, isLoading, onSendMessage }) {
  const [input, setInput] = useState('');
  const bottomRef = useRef(null);

  // Auto-scroll to bottom whenever messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  function handleSubmit(e) {
    e.preventDefault();
    if (!input.trim() || isLoading) return;
    onSendMessage(input.trim());
    setInput('');
  }

  function handleKeyDown(e) {
    // Submit on Enter (but not Shift+Enter)
    if (e.key === 'Enter' && !e.shiftKey) {
      handleSubmit(e);
    }
  }

  return (
    <div className="flex flex-col flex-1 bg-white rounded-2xl border-4 border-poke-red shadow-xl overflow-hidden">
      {/* ── Message list ── */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 min-h-[400px] max-h-[65vh]">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center text-gray-400 space-y-3">
            <div className="text-5xl">⚡</div>
            <p className="font-pixel text-xs leading-loose text-poke-red-dark opacity-70">
              Ask me anything about Pokemon!
            </p>
            <div className="text-xs space-y-1 text-gray-400">
              <p>"What are Charizard's stats?"</p>
              <p>"What's the lore behind Cubone?"</p>
              <p>"Build a team to counter Garchomp"</p>
              <p>"Water types weak to Electric?"</p>
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <MessageBubble key={i} message={msg} />
        ))}

        {/* Typing indicator while waiting for response */}
        {isLoading && (
          <div className="flex items-center gap-2 px-4 py-3">
            <div className="flex gap-1">
              <div className="dot" />
              <div className="dot" />
              <div className="dot" />
            </div>
            <span className="text-xs text-gray-400">PokeAgent is thinking...</span>
          </div>
        )}

        {/* Invisible anchor for auto-scroll */}
        <div ref={bottomRef} />
      </div>

      {/* ── Input bar ── */}
      <div className="border-t-4 border-poke-cream-dark bg-poke-cream p-3">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about a Pokemon..."
            disabled={isLoading}
            className="flex-1 px-4 py-2 rounded-xl border-2 border-poke-cream-dark bg-white
                       focus:outline-none focus:border-poke-red text-sm
                       disabled:opacity-50 disabled:cursor-not-allowed"
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="px-5 py-2 bg-poke-red text-white rounded-xl font-semibold text-sm
                       hover:bg-poke-red-dark transition-colors
                       disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
