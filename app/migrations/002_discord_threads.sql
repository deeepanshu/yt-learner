CREATE TABLE discord_threads (
    id BIGSERIAL PRIMARY KEY,
    guild_id TEXT NOT NULL,
    parent_channel_id BIGINT NOT NULL,
    purpose TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_key TEXT NOT NULL,
    thread_id BIGINT NOT NULL,
    title TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (guild_id, parent_channel_id, purpose, source_type, source_key)
);

CREATE INDEX idx_discord_threads_thread_id ON discord_threads (thread_id);
