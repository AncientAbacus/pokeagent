import React, { useState } from 'react';
import axios from 'axios';
import ChatWindow from './components/ChatWindow';

const API_URL = 'http://localhost:8000';

/**
 * App
 * ---
 * Root component. Owns all conversation state and the sendMessage function.
 *
 * State shape for each message:
 *   { role: 'user' | 'assistant', content: string,
 *     toolCalls: Array, reasoning: string }
 *
 * Why keep history here?
 * The backend needs the full conversation history to give multi-turn answers.
 * We pass history (stripped to {role, content}) on each request.
 */
export default function App() {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  async function sendMessage(text) {
    if (!text.trim()) return;

    // Append user message immediately for instant feedback
    const userMsg = { role: 'user', content: text, toolCalls: [], reasoning: '' };
    const updatedMessages = [...messages, userMsg];
    setMessages(updatedMessages);
    setIsLoading(true);
    setError(null);

    // Build history for the API (all turns except the one we just added)
    const history = messages.map(m => ({ role: m.role, content: m.content }));

    try {
      const res = await axios.post(`${API_URL}/chat`, {
        message: text,
        history,
      });

      const botMsg = {
        role: 'assistant',
        content: res.data.answer,
        toolCalls: res.data.tool_calls || [],
        reasoning: res.data.reasoning || '',
      };
      setMessages([...updatedMessages, botMsg]);
    } catch (err) {
      const detail = err.response?.data?.detail || err.message;
      setError(`Error: ${detail}`);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-poke-cream flex flex-col">
      {/* ── Header ── */}
      <header className="bg-poke-red shadow-lg">
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center gap-3">
          {/* Pokedex button decoration */}
          <div className="flex gap-2 items-center">
            <div className="w-8 h-8 rounded-full bg-white border-4 border-poke-red-dark shadow-inner" />
            <div className="w-3 h-3 rounded-full bg-red-300" />
            <div className="w-3 h-3 rounded-full bg-yellow-300" />
            <div className="w-3 h-3 rounded-full bg-green-300" />
          </div>
          <h1 className="font-pixel text-white text-sm tracking-wide ml-2">
            PokeAgent
          </h1>
          <span className="text-red-200 text-xs ml-auto hidden sm:block">
            AI Pokemon Research Assistant
          </span>
        </div>
      </header>

      {/* ── Main ── */}
      <main className="flex-1 max-w-4xl w-full mx-auto px-4 py-6 flex flex-col">
        <ChatWindow
          messages={messages}
          isLoading={isLoading}
          onSendMessage={sendMessage}
        />
        {error && (
          <div className="mt-2 p-3 bg-red-100 border border-poke-red rounded text-sm text-poke-red-dark">
            {error}
          </div>
        )}
      </main>
    </div>
  );
}
