# PokeAgent: AI Pokemon Research Assistant

A full-stack RAG + AI agent application that answers natural language questions about Pokemon. Built to demonstrate deep skills in retrieval-augmented generation (RAG), agent orchestration, and full-stack development.

## Features

- **RAG-powered lore retrieval** - Ask about Pokemon lore and get accurate Pokedex entries
- **Structured data queries** - Find Pokemon by type, stats, moves, and abilities
- **Type advantage analysis** - Instant type matchup lookups
- **Team recommendations** - Multi-step agent reasoning for competitive team building
- **Reasoning transparency** - See exactly which tools the agent used and why

## Quick Start

### Prerequisites
- Python 3.9+
- Node.js 16+
- OpenAI API key

### Setup

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Copy env template and add your OpenAI key
cp .env.example .env

# 3. Ingest Gen 1 into SQLite (~40s; use --limit 1025 for the full Dex)
python -m data.ingest

# 4. Embed flavor text into ChromaDB (downloads all-MiniLM-L6-v2 on first run)
python -m rag.embedder

# 5. Start the backend
python -m uvicorn api.main:app --reload

# 6. In another terminal, start the frontend
cd frontend && npm install && npm start
```

Visit `http://localhost:3000` to chat with PokeAgent.

## Project Architecture

```
User Query
    ↓
Frontend (React Chat UI)
    ↓
Backend (FastAPI)
    ↓
Agent (LangGraph)
    ├──→ tools.get_pokemon_stats() ──→ SQLite
    ├──→ tools.search_by_criteria() ──→ SQLite
    ├──→ tools.retrieve_lore() ────────→ ChromaDB (RAG)
    ├──→ tools.get_type_matchups() (logic-based)
    └──→ tools.suggest_counter_team() (multi-step)
    ↓
Response + Reasoning Trace
    ↓
Frontend Displays Answer + Tool Calls
```

## Project Structure

```
pokeagent/
├── data/          # Data ingestion & SQLite
├── rag/           # Embeddings & ChromaDB retrieval
├── agent/         # LangGraph agent & tools
├── api/           # FastAPI backend
├── frontend/      # React UI
└── evals/         # Test set & RAGAS evaluation
```

## Build Order

Follow this sequence (each stage builds on the last):

1. ✗ **Data Ingestion** - Fetch from PokeAPI, populate SQLite + cache
2. ✗ **RAG Pipeline** - Embed flavor text, store in ChromaDB
3. ✗ **Agent Tools** - Implement & unit test each tool
4. ✗ **Agent Graph** - Build LangGraph orchestration
5. ✗ **FastAPI Backend** - Chat endpoint with streaming
6. ✗ **React Frontend** - Chat UI + reasoning trace panel
7. ✗ **Eval Harness** - Test set + RAGAS metrics

## About

Built by Gino Angelici as a portfolio project to demonstrate:
- Deep RAG implementation (chunking strategies, embeddings, retrieval)
- Agent design (tool orchestration, reasoning loops, multi-hop queries)
- Full-stack development (Python backend, React frontend)
- Production code quality (type hints, tests, error handling)

See [CLAUDE.md](./CLAUDE.md) for detailed implementation notes and design decisions.
