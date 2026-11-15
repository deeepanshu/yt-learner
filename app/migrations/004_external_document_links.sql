CREATE TABLE external_document_links (
    id BIGSERIAL PRIMARY KEY,
    provider TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_key TEXT NOT NULL,
    remote_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (provider, source_type, source_key)
);

CREATE INDEX idx_external_document_links_remote_id
    ON external_document_links (provider, remote_id);
