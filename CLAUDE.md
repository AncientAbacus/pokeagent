# PokeAgent -- AI Pokemon Research Assistant

## Project Vision

A full-stack RAG + AI agent app where users can ask natural language questions about Pokemon.
The app handles lore/narrative questions via RAG, structured queries via tool calls, and complex
multi-step questions (like team building) via agent reasoning. Built as a portfolio project to
demonstrate deep RAG and agentic AI skills.

## Example User Queries

- "What's the best team to counter a Garchomp?"
- "Find me a Water-type Pokemon under base 400 BST that can learn Ice Beam"
- "Compare Gengar and Haunter's competitive viability"
- "What's the lore behind Cubone?"

## Architecture Overview

```
PokeAPI (REST)
     |
     v
Data Ingestion Layer
     |
     +-- Structured data (stats, types, moves, abilities, evolutions) --> SQLite/Postgres
     +-- Flavor text / Pokedex entries (~8,000+ entries)              --> ChromaDB (vector DB)
     |
     v
Agent Layer (LangGraph or custom)
     |
     +-- Tool: get_pokemon_stats(name)
     +-- Tool: search_by_criteria(type, min_bst, max_bst, move)
     +-- Tool: get_type_matchups(type)
     +-- Tool: retrieve_lore(query)          <-- RAG call into ChromaDB
     +-- Tool: suggest_counter_team(pokemon) <-- multi-step reasoning
     |
     v
Backend API (FastAPI)
     |
     v
Frontend (React)
     |
     +-- Chat UI with Pokedex aesthetic
     +-- Pokemon sprites from PokeAPI
     +-- Collapsible reasoning trace panel (shows agent tool calls)
     |
     v
Eval Harness (RAGAS)
     +-- Retrieval precision and faithfulness metrics
     +-- 20+ hand-labeled Q&A test set
```

## Tech Stack

| Layer       | Choice                                      |
|-------------|---------------------------------------------|
| Language    | Python (backend), JavaScript/React (frontend)|
| LLM         | OpenAI API (gpt-4o or gpt-4o-mini)          |
| Embeddings  | sentence-transformers or OpenAI embeddings  |
| Vector DB   | ChromaDB (local dev), Qdrant (prod option)  |
| Structured DB | SQLite (dev), Postgres (prod option)      |
| Agent framework | LangGraph (preferred) or custom         |
| Backend API | FastAPI                                     |
| Frontend    | React + Tailwind CSS                        |
| Evals       | RAGAS                                       |
| Data source | PokeAPI (https://pokeapi.co/) -- free, no auth required |

## Repo Structure

```
pokeagent/
├── CLAUDE.md                  # This file
├── README.md
├── .env.example               # API keys template (never commit .env)
├── requirements.txt
├── package.json               # Frontend deps
│
├── data/
│   ├── ingest.py              # Pull from PokeAPI, store structured + embeddings
│   ├── schema.sql             # SQLite schema
│   └── raw/                   # Cached PokeAPI responses (gitignore large files)
│
├── rag/
│   ├── embedder.py            # Chunk + embed Pokedex flavor text
│   ├── retriever.py           # Query ChromaDB, return top-k chunks
│   └── chroma_db/             # Local ChromaDB storage (gitignored)
│
├── agent/
│   ├── tools.py               # All tool definitions (stats, search, lore, matchups)
│   ├── agent.py               # LangGraph agent graph definition
│   └── prompts.py             # System prompts for the agent
│
├── api/
│   └── main.py                # FastAPI app, /chat endpoint, streaming support
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── ChatWindow.jsx
│   │   │   ├── MessageBubble.jsx
│   │   │   ├── ReasoningTrace.jsx   # Collapsible agent tool call panel
│   │   │   └── PokemonCard.jsx
│   │   └── index.css
│   └── public/
│
└── evals/
    ├── test_set.json          # Hand-labeled Q&A pairs
    └── run_evals.py           # RAGAS evaluation runner
```

## Build Order

Follow this sequence -- each stage builds on the last:

1. **Data ingestion** (`data/ingest.py`)
   - Fetch all Pokemon from PokeAPI (use `/api/v2/pokemon?limit=10000`)
   - Store structured data (stats, types, moves, abilities) in SQLite
   - Fetch and store all Pokedex flavor text entries per Pokemon
   - Cache raw API responses locally to avoid re-fetching

2. **RAG pipeline** (`rag/`)
   - Chunk flavor text entries (one entry per chunk is natural here)
   - Embed with sentence-transformers (`all-MiniLM-L6-v2` is a good start)
   - Store in ChromaDB with metadata (pokemon_name, generation, game_version)
   - Build retriever with top-k search + metadata filtering

3. **Agent tools** (`agent/tools.py`)
   - Implement each tool as a standalone testable function
   - Write unit tests for each tool before wiring into the agent

4. **Agent graph** (`agent/agent.py`)
   - Define LangGraph graph with tool-calling node and reasoning loop
   - Test with a set of diverse queries before connecting to API

5. **FastAPI backend** (`api/main.py`)
   - POST /chat endpoint accepting { message, history }
   - Stream agent responses using Server-Sent Events (SSE)
   - Return tool call trace alongside final answer

6. **React frontend** (`frontend/`)
   - Chat UI first, then add reasoning trace panel
   - Fetch sprites from `https://pokeapi.co/api/v2/pokemon/{id}` (sprites field)
   - Pokedex red/cream color scheme

7. **Eval harness** (`evals/`)
   - Write 20+ Q&A pairs covering lore, stats, type matchups, and recommendations
   - Run RAGAS metrics: faithfulness, answer relevance, context precision
   - Log results to a markdown report

## Code Style and Conventions

- Python: use type hints everywhere, docstrings on all functions
- Keep tools atomic and independently testable
- Never hardcode API keys -- use python-dotenv and .env file
- Log agent reasoning steps (tool name, input, output) for debugging and the frontend trace
- Async FastAPI endpoints (use `async def`)
- React components should be functional with hooks only

## Key Implementation Notes

### PokeAPI Usage
- Rate limit: 100 requests/minute (unauthenticated). Cache aggressively.
- Flavor text comes from `/api/v2/pokemon-species/{id}` under `flavor_text_entries`
- Filter flavor text to English only (`language.name == "en"`)
- Deduplicate flavor text -- many entries repeat across game versions

### RAG Chunking Strategy
- Each individual Pokedex flavor text entry = one chunk (they are naturally short, ~1-3 sentences)
- Include metadata: pokemon_name, national_dex_number, game_version, generation
- This allows filtered retrieval (e.g., "lore from Gen 1 only")

### Type Matchup Logic
- Implement a full 18x18 type effectiveness table in Python (do not rely on LLM for this)
- This ensures the `get_type_matchups` tool is always accurate

### Agent Reasoning
- The reasoning trace (tool calls + inputs + outputs) should be captured and returned to
  the frontend so users can see how the agent arrived at its answer. This is a key
  portfolio differentiator.

### Eval Test Set
- Cover all tool types: at least 5 lore questions, 5 stat/filter questions,
  5 type matchup questions, 5 recommendation questions
- Include some multi-hop questions that require 2+ tool calls

## Environment Variables (.env)

```
OPENAI_API_KEY=your_key_here
EMBEDDING_MODEL=all-MiniLM-L6-v2
CHROMA_PERSIST_DIR=./rag/chroma_db
SQLITE_DB_PATH=./data/pokeagent.db
```

## About the Developer

- Gino Angelici, UCSD Data Science graduate (BS, June 2025)
- Background in ML research (autonomous vehicles, climate data), Deloitte data science internship
- Strong in Python, SQL, PyTorch, TensorFlow, AWS, Spark, D3.js, React
- Building this project to deepen RAG and agentic AI skills for job search
- Prefers clean, well-documented, production-quality code
