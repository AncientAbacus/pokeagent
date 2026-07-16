"""
FastAPI Backend for PokeAgent
==============================

Exposes a single POST /chat endpoint that:
1. Accepts a user message + conversation history
2. Passes them to the LangGraph agent
3. Returns the answer + full reasoning trace (tool calls)

Run from project root:
    uvicorn api.main:app --reload --port 8000

The agent is initialized once on startup (avoids reloading the LLM client
on every request).
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from dotenv import load_dotenv

# Ensure project root is on sys.path when running as a module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Agent singleton — initialized once at startup, reused across requests
_agent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the LangGraph agent on server start."""
    global _agent
    if not os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") == "your_openai_api_key_here":
        logger.warning("OPENAI_API_KEY not set — agent will fail on real queries")
    else:
        try:
            from agent.agent import PokeAgent
            logger.info("Initializing PokeAgent...")
            _agent = PokeAgent()
            logger.info("PokeAgent ready")
        except Exception as e:
            logger.error(f"Failed to initialize agent: {e}")
    yield


app = FastAPI(
    title="PokeAgent API",
    description="AI Pokemon research assistant with RAG and tool-calling",
    version="1.0.0",
    lifespan=lifespan
)

# Allow requests from the React dev server (localhost:3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request / Response Models ────────────────────────────────────────────────

class ChatMessage(BaseModel):
    """A single turn in the conversation history."""
    role: str   # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    """Incoming chat request."""
    message: str
    history: Optional[List[ChatMessage]] = []


class ToolCallRecord(BaseModel):
    """A single tool invocation captured during agent reasoning."""
    tool: str
    input: Dict[str, Any]
    output: Any


class ChatResponse(BaseModel):
    """Response returned to the frontend."""
    answer: str
    tool_calls: List[ToolCallRecord]
    reasoning: str


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    """Simple health check — useful for frontend to detect server state."""
    return {
        "status": "ok",
        "agent_ready": _agent is not None
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Run the PokeAgent on a user message.

    Accepts:
        { "message": "...", "history": [ {"role": "user", "content": "..."}, ... ] }

    Returns:
        { "answer": "...", "tool_calls": [...], "reasoning": "..." }
    """
    if _agent is None:
        raise HTTPException(
            status_code=503,
            detail="Agent not initialized. Check OPENAI_API_KEY in .env"
        )

    # Convert history dicts to LangChain message objects
    from langchain_core.messages import HumanMessage, AIMessage
    lc_history = []
    for msg in (request.history or []):
        if msg.role == "user":
            lc_history.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            lc_history.append(AIMessage(content=msg.content))

    try:
        # agent.run() is synchronous (LangGraph invoke is blocking)
        # Run it in a thread pool so we don't block the event loop
        result = await asyncio.to_thread(
            _agent.run,
            request.message,
            lc_history
        )
    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    return ChatResponse(
        answer=result["answer"],
        tool_calls=[
            ToolCallRecord(
                tool=tc["tool"],
                input=tc["input"],
                output=tc["output"]
            )
            for tc in result.get("tool_calls", [])
        ],
        reasoning=result.get("reasoning", "")
    )
