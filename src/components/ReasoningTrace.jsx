import React, { useState } from 'react';

/**
 * ReasoningTrace
 * --------------
 * Collapsible panel showing every tool call the agent made.
 * This is the key portfolio differentiator — it makes AI reasoning transparent.
 *
 * Props:
 *   toolCalls: Array of { tool: string, input: object, output: any }
 *
 * Why this matters for an interview:
 *   "I made the agent's chain-of-thought visible. Users can see exactly which
 *    tools were called, with what parameters, and what data came back. This
 *    builds trust and makes the system debuggable."
 */
export default function ReasoningTrace({ toolCalls }) {
  const [isOpen, setIsOpen] = useState(false);

  if (!toolCalls || toolCalls.length === 0) return null;

  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden text-xs font-mono">
      {/* Toggle header */}
      <button
        onClick={() => setIsOpen(o => !o)}
        className="w-full flex items-center justify-between px-3 py-2
                   bg-gray-50 hover:bg-gray-100 transition-colors text-left"
      >
        <span className="text-gray-500 flex items-center gap-2">
          <span className={`transition-transform ${isOpen ? 'rotate-90' : ''}`}>▶</span>
          <span>
            {toolCalls.length} tool call{toolCalls.length > 1 ? 's' : ''} — view reasoning
          </span>
        </span>
      </button>

      {/* Expanded content */}
      {isOpen && (
        <div className="divide-y divide-gray-100 bg-white">
          {toolCalls.map((call, i) => (
            <ToolCallRow key={i} index={i + 1} call={call} />
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * ToolCallRow
 * -----------
 * Displays one tool call with input → output.
 */
function ToolCallRow({ index, call }) {
  const outputStr = JSON.stringify(call.output, null, 2);
  // Truncate very long outputs in the display
  const truncated = outputStr.length > 400
    ? outputStr.slice(0, 400) + '\n...(truncated)'
    : outputStr;

  return (
    <div className="p-3 space-y-2">
      {/* Tool name */}
      <div className="flex items-center gap-2">
        <span className="bg-poke-red text-white rounded px-1.5 py-0.5 text-xs">
          {index}
        </span>
        <span className="font-bold text-poke-red-dark">{call.tool}</span>
      </div>

      {/* Input */}
      <div>
        <span className="text-gray-400 text-xs uppercase tracking-wider">Input</span>
        <pre className="mt-1 bg-gray-50 rounded p-2 text-gray-700 overflow-x-auto text-xs leading-relaxed">
          {JSON.stringify(call.input, null, 2)}
        </pre>
      </div>

      {/* Output */}
      <div>
        <span className="text-gray-400 text-xs uppercase tracking-wider">Output</span>
        <pre className="mt-1 bg-poke-screen bg-opacity-30 rounded p-2 text-gray-700 overflow-x-auto text-xs leading-relaxed">
          {truncated}
        </pre>
      </div>
    </div>
  );
}
