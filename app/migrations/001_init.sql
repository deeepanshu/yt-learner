CREATE TABLE sources (
    id BIGSERIAL PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_key TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    title TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (source_type, source_key)
);

CREATE TABLE learning_records (
    id BIGSERIAL PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES sources (id),
    record_type TEXT NOT NULL,
    title TEXT NOT NULL,
    filename TEXT NOT NULL,
    markdown TEXT NOT NULL,
    requested_by TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (source_id, record_type)
);

CREATE TABLE jobs (
    id BIGSERIAL PRIMARY KEY,
    task_type TEXT NOT NULL,
    source TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    input_json JSONB NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    learning_record_id BIGINT,
    result_filename TEXT,
    error TEXT
);

CREATE TABLE watched_channels (
    id BIGSERIAL PRIMARY KEY,
    guild_id TEXT NOT NULL,
    youtube_channel_id TEXT NOT NULL,
    youtube_channel_ref TEXT NOT NULL,
    youtube_channel_title TEXT NOT NULL,
    discord_channel_id BIGINT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    bootstrap_completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (guild_id, youtube_channel_id)
);

CREATE TABLE watched_channel_videos (
    id BIGSERIAL PRIMARY KEY,
    watched_channel_id BIGINT NOT NULL REFERENCES watched_channels (id),
    video_id TEXT NOT NULL,
    video_url TEXT NOT NULL,
    title TEXT NOT NULL,
    published_at TIMESTAMPTZ,
    discovered_at TIMESTAMPTZ NOT NULL,
    queued_job_id BIGINT,
    learning_record_id BIGINT,
    UNIQUE (watched_channel_id, video_id)
);

CREATE TABLE debug_artifacts (
    id BIGSERIAL PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_key TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    filename TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_jobs_status_priority_id ON jobs (status, priority DESC, id);
CREATE INDEX idx_sources_type_key ON sources (source_type, source_key);
CREATE INDEX idx_watched_channels_active ON watched_channels (is_active, id);
CREATE INDEX idx_watched_channel_videos_job ON watched_channel_videos (queued_job_id);
CREATE INDEX idx_debug_artifacts_source ON debug_artifacts (source_type, source_key, created_at DESC);
