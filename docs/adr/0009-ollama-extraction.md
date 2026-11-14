# ADR 0009: Extract notes with Ollama Cloud

## Status

Accepted

## Date

2026-11-14

## Context

Extraction used OpenAI `responses.create` and `OPENAI_API_KEY` / `OPENAI_MODEL`. Komodo already has `OLLAMA_API_KEY` and `OLLAMA_MODEL` (Ollama Cloud).

Ollama's OpenAI-compatible API is chat completions, not the Responses API.

## Decision

- Require `OLLAMA_API_KEY` and `OLLAMA_MODEL`.
- Default `OLLAMA_BASE_URL` to `https://ollama.com/v1`.
- Keep the OpenAI Python SDK as the HTTP client, pointed at that base URL.
- Call `chat.completions.create`.

## Consequences

Local Ollama is possible later by setting `OLLAMA_BASE_URL` (e.g. `http://ollama.lab:11434/v1`).
