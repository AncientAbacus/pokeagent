"""
LangGraph Agent for PokeAgent
=============================

How the agent reasoning loop works:
1. User message + system prompt → LLM
2. LLM decides to call a tool → ToolNode executes it
3. Tool output goes back to LLM as a ToolMessage
4. Repeat until LLM gives a final text answer (no more tool calls)

Key LangGraph 1.x concepts:
- MessagesState: built-in state type that accumulates messages
- ToolNode: handles all tool dispatch automatically (replaces old ToolExecutor)
- tools_condition: built-in router — routes to "tools" if LLM made tool calls,
                    otherwise routes to END
"""

import json
import logging
from typing import Any, List, Dict, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, MessagesState, END
from langgraph.prebuilt import ToolNode, tools_condition

# Import our tools
from agent.tools import (
    get_pokemon_stats,
    search_by_criteria,
    get_type_matchups,
    retrieve_lore,
    suggest_counter_team
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# LLM
# ============================================================================

def create_llm() -> ChatOpenAI:
    """Initialize OpenAI LLM."""
    return ChatOpenAI(model="gpt-4o-mini", temperature=0.7)


# ============================================================================
# Tool definitions
# ============================================================================

def create_tools() -> list:
    """
    Wrap our Pokemon functions as LangChain tools.

    The @tool decorator:
    - Reads the function name → becomes the tool name the LLM sees
    - Reads the docstring   → becomes the tool description the LLM uses
    - Reads type hints       → generates the JSON schema for parameters
    """

    @tool
    def pokemon_stats(pokemon_name: str) -> dict:
        """
        Get detailed stats for a Pokemon (HP, ATK, DEF, SPD, BST, abilities, types).

        Use this when the user asks about a Pokemon's strengths, weaknesses, or stats.
        """
        result = get_pokemon_stats(pokemon_name)
        return result or {"error": f"Pokemon '{pokemon_name}' not found in database"}

    @tool
    def search_pokemon(
        type_filter: Optional[str] = None,
        min_bst: Optional[int] = None,
        max_bst: Optional[int] = None,
        move: Optional[str] = None,
        ability: Optional[str] = None,
        limit: int = 10
    ) -> list:
        """
        Find Pokemon matching criteria (type, BST range, move, or ability).

        Use this when the user asks:
        - "Find Water types under 400 BST"
        - "Pokemon that can learn Ice Beam"
        - "Fighting types with high attack"
        """
        return search_by_criteria(
            type_filter=type_filter,
            min_bst=min_bst,
            max_bst=max_bst,
            move=move,
            ability=ability,
            limit=limit
        )

    @tool
    def type_matchups(pokemon_type: str) -> dict:
        """
        Get type effectiveness data: what does this type beat, resist, and lose to?

        Use this for questions about competitive viability, type advantages,
        or when building a counter team.
        """
        return get_type_matchups(pokemon_type)

    @tool
    def pokemon_lore(query: str, k: int = 5) -> list:
        """
        Retrieve Pokemon lore and Pokedex flavor text via semantic search.

        Use this for questions about Pokemon origins, legendary stories, or
        Pokedex entries. Examples:
        - "What's the lore behind Cubone?"
        - "Describe Mewtwo's origin"
        """
        return retrieve_lore(query, k=k)

    @tool
    def suggest_team(target_pokemon: str, team_size: int = 3) -> dict:
        """
        Suggest a counter team for a target Pokemon.

        Use this when the user asks:
        - "What's the best team to counter Garchomp?"
        - "How do I beat a Charizard?"
        """
        return suggest_counter_team(target_pokemon, team_size=team_size)

    return [pokemon_stats, search_pokemon, type_matchups, pokemon_lore, suggest_team]


# ============================================================================
# Agent class
# ============================================================================

class PokeAgent:
    """
    Multi-turn Pokemon agent built on LangGraph.

    The graph has two nodes:
      agent  →  calls LLM (may request tool calls)
      tools  →  ToolNode executes any requested tools

    Routing:
      agent --[has tool calls?]--> tools --> agent (loop)
           --[no tool calls] --> END
    """

    def __init__(self):
        self.llm = create_llm()
        self.tools = create_tools()
        self.llm_with_tools = self.llm.bind_tools(self.tools)
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Construct the reasoning loop as a LangGraph StateGraph."""

        workflow = StateGraph(MessagesState)

        # Node 1: Agent reasons and decides whether to call tools
        def agent_node(state: MessagesState) -> dict:
            logger.info("Agent reasoning...")
            response = self.llm_with_tools.invoke(state["messages"])
            # Returning {"messages": [response]} appends to state via add_messages
            return {"messages": [response]}

        # Node 2: ToolNode automatically dispatches every tool call in the
        #          last AIMessage and returns ToolMessage results
        tool_node = ToolNode(self.tools)

        workflow.add_node("agent", agent_node)
        workflow.add_node("tools", tool_node)

        workflow.set_entry_point("agent")

        # tools_condition routes to "tools" if LLM made tool calls, else END
        workflow.add_conditional_edges("agent", tools_condition)

        # After tools run, go back to agent for synthesis
        workflow.add_edge("tools", "agent")

        return workflow.compile()

    def run(
        self,
        user_query: str,
        conversation_history: Optional[List[BaseMessage]] = None
    ) -> Dict[str, Any]:
        """
        Run the agent on a user query.

        Args:
            user_query: Natural language question
            conversation_history: Previous messages (for multi-turn)

        Returns:
            {
                'answer':     Final response text,
                'tool_calls': List of {tool, input, output},
                'reasoning':  Formatted trace string,
                'messages':   Full message list (pass back for next turn)
            }
        """
        from agent.prompts import SYSTEM_PROMPT

        messages = (
            [SystemMessage(content=SYSTEM_PROMPT)]
            + (conversation_history or [])
            + [HumanMessage(content=user_query)]
        )

        logger.info(f"Query: {user_query[:80]}")
        final_state = self.graph.invoke({"messages": messages})

        # Extract tool call records by pairing AIMessage tool_calls with
        # the corresponding ToolMessage results
        tool_calls = _extract_tool_calls(final_state["messages"])

        last_message = final_state["messages"][-1]
        return {
            "answer": last_message.content,
            "tool_calls": tool_calls,
            "reasoning": _format_reasoning(tool_calls),
            "messages": final_state["messages"],
        }


# ============================================================================
# Helpers
# ============================================================================

def _extract_tool_calls(messages: List[BaseMessage]) -> List[Dict[str, Any]]:
    """
    Walk through the message history and pair each tool call request
    with its result message.

    LangGraph produces this pattern:
        AIMessage(tool_calls=[{id: "...", name: "...", args: {...}}])
        ToolMessage(tool_call_id="...", content="<json result>")
    """
    # Build lookup: tool_call_id → ToolMessage content
    result_by_id: Dict[str, Any] = {}
    for msg in messages:
        if hasattr(msg, "tool_call_id") and msg.tool_call_id:
            try:
                result_by_id[msg.tool_call_id] = json.loads(msg.content)
            except (json.JSONDecodeError, TypeError):
                result_by_id[msg.tool_call_id] = msg.content

    # Collect paired records in order
    tool_calls = []
    for msg in messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append({
                    "tool":   tc["name"],
                    "input":  tc["args"],
                    "output": result_by_id.get(tc["id"], "no result found"),
                })
    return tool_calls


def _format_reasoning(tool_calls: List[Dict]) -> str:
    """Format tool calls as a human-readable reasoning trace."""
    if not tool_calls:
        return "No tools used (LLM answered directly)"

    trace = "Tool Usage:\n"
    for i, call in enumerate(tool_calls, 1):
        trace += f"\n{i}. {call['tool']}\n"
        trace += f"   Input:  {json.dumps(call['input'])}\n"
        output_str = json.dumps(call['output'])[:200]
        trace += f"   Output: {output_str}...\n"
    return trace


# ============================================================================
# Quick test
# ============================================================================

def main():
    """Test the agent (requires OPENAI_API_KEY in .env)."""
    import os
    from dotenv import load_dotenv
    load_dotenv()

    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY not set. Add it to .env to test the agent.")
        return

    agent = PokeAgent()
    print("\n" + "="*60)
    print("PokeAgent ready")
    print("="*60)

    result = agent.run("What are Charizard's stats?")
    print(f"\nAnswer: {result['answer']}\n")
    print(f"Reasoning:\n{result['reasoning']}")


if __name__ == "__main__":
    main()
