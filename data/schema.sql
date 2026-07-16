-- Pokemon structured data schema
-- This is the foundation for all stat queries and type-based searches

CREATE TABLE IF NOT EXISTS pokemon (
    id INTEGER PRIMARY KEY,
    national_dex_number INTEGER UNIQUE NOT NULL,
    name TEXT UNIQUE NOT NULL,
    height_dm INTEGER,
    weight_hg INTEGER,
    base_experience INTEGER,
    is_default BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pokemon_stats (
    id INTEGER PRIMARY KEY,
    pokemon_id INTEGER NOT NULL UNIQUE,
    hp INTEGER,
    attack INTEGER,
    defense INTEGER,
    sp_atk INTEGER,
    sp_def INTEGER,
    speed INTEGER,
    bst INTEGER AS (hp + attack + defense + sp_atk + sp_def + speed) STORED,
    FOREIGN KEY(pokemon_id) REFERENCES pokemon(id)
);

CREATE TABLE IF NOT EXISTS pokemon_types (
    id INTEGER PRIMARY KEY,
    pokemon_id INTEGER NOT NULL,
    type_name TEXT NOT NULL,
    slot INTEGER NOT NULL,
    FOREIGN KEY(pokemon_id) REFERENCES pokemon(id),
    UNIQUE(pokemon_id, type_name)
);

CREATE TABLE IF NOT EXISTS pokemon_abilities (
    id INTEGER PRIMARY KEY,
    pokemon_id INTEGER NOT NULL,
    ability_name TEXT NOT NULL,
    is_hidden BOOLEAN DEFAULT FALSE,
    FOREIGN KEY(pokemon_id) REFERENCES pokemon(id)
);

CREATE TABLE IF NOT EXISTS pokemon_moves (
    id INTEGER PRIMARY KEY,
    pokemon_id INTEGER NOT NULL,
    move_name TEXT NOT NULL,
    learn_method TEXT,
    FOREIGN KEY(pokemon_id) REFERENCES pokemon(id),
    UNIQUE(pokemon_id, move_name)
);

-- Pokedex flavor text for RAG (stored as separate entries for fine-grained retrieval)
CREATE TABLE IF NOT EXISTS pokemon_flavor_text (
    id INTEGER PRIMARY KEY,
    pokemon_id INTEGER NOT NULL,
    pokemon_name TEXT NOT NULL,
    national_dex_number INTEGER NOT NULL,
    flavor_text TEXT NOT NULL,
    game_version TEXT,
    generation INTEGER,
    language TEXT DEFAULT 'en',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(pokemon_id) REFERENCES pokemon(id),
    UNIQUE(pokemon_id, game_version, flavor_text)
);

-- Indices for common queries
CREATE INDEX IF NOT EXISTS idx_pokemon_name ON pokemon(name);
CREATE INDEX IF NOT EXISTS idx_pokemon_type ON pokemon_types(type_name);
CREATE INDEX IF NOT EXISTS idx_pokemon_stats_bst ON pokemon_stats(bst);
CREATE INDEX IF NOT EXISTS idx_flavor_text_pokemon ON pokemon_flavor_text(pokemon_id);
CREATE INDEX IF NOT EXISTS idx_flavor_text_generation ON pokemon_flavor_text(generation);
