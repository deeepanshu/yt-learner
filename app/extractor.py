from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from openai import AsyncOpenAI

from app.transcript import TranscriptData

SYSTEM_PROMPT = (
    "You create concise but useful learning notes from YouTube transcripts.\n"
    "Return markdown only.\n"
    "Use this structure exactly:\n"
    "# <Video Title>\n\n"
    "Source: <YouTube URL>\n"
    "Processed: <ISO-8601 timestamp>\n\n"
    "## Summary\n\n"
    "<short summary>\n\n"
    "## Topics\n\n"
    "### <Topic>\n"
    "- Key point\n"
    "- Practical takeaway\n\n"
    "## Actionable Notes\n\n"
    "- Action item\n"
)


@dataclass(frozen=True)
class ExtractionInput:
    title: str
    url: str
    transcript: TranscriptData


class ExtractionError(RuntimeError):
    """Raised when markdown extraction fails."""


class LearningExtractor:
    def __init__(self, *, api_key: str, model: str, max_transcript_chars: int | None = None) -> None:
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.max_transcript_chars = max_transcript_chars

    async def render_markdown(self, payload: ExtractionInput) -> str:
        processed_at = datetime.now(timezone.utc).isoformat()
        try:
            response = await self.client.responses.create(
                model=self.model,
                input=build_messages(
                    payload=payload,
                    processed_at=processed_at,
                    max_transcript_chars=self.max_transcript_chars,
                ),
            )
        except Exception as exc:
            raise ExtractionError("OpenAI extraction request failed") from exc

        markdown = (response.output_text or "").strip()
        if not markdown:
            raise ExtractionError("OpenAI extraction returned empty markdown")
        return markdown


def build_messages(
    *,
    payload: ExtractionInput,
    processed_at: str,
    max_transcript_chars: int | None = None,
) -> list[dict[str, str]]:
    transcript_text = payload.transcript.text
    if max_transcript_chars is not None:
        transcript_text = transcript_text[:max_transcript_chars]

    user_prompt = (
        f"Video title: {payload.title}\n"
        f"Video URL: {payload.url}\n"
        f"Processed timestamp: {processed_at}\n\n"
        "Transcript:\n"
        f"{transcript_text}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
