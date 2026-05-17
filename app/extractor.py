from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from openai import AsyncOpenAI

from app.transcript import TranscriptData

SYSTEM_PROMPT = (
    "You create deep learning notes from YouTube transcripts.\n"
    "Return markdown only.\n"
    "Optimize for helping the reader actually learn, not for brevity.\n"
    "Avoid generic summaries and vague bullets.\n"
    "Explain the important ideas clearly enough that someone can revisit the notes later and recover the main lessons.\n"
    "When the speaker gives reasoning, tradeoffs, frameworks, examples, or implementation advice, preserve those details.\n"
    "Do not invent facts that are not supported by the transcript.\n"
    "Use this structure exactly:\n"
    "# <Video Title>\n\n"
    "Source: <YouTube URL>\n"
    "Processed: <ISO-8601 timestamp>\n\n"
    "## Summary\n\n"
    "Write 2-4 solid paragraphs covering the core argument, what problem is being addressed, and the most important conclusions.\n\n"
    "## Key Ideas\n\n"
    "- 5 to 10 specific ideas, principles, or claims from the video\n"
    "- Each bullet should be informative, not a fragment\n\n"
    "## Topics\n\n"
    "### <Topic>\n"
    "- Explanation: explain the concept in 2-4 detailed bullets\n"
    "- Why it matters: describe why the topic matters in practice\n"
    "- Example or method: include any concrete technique, workflow, or example from the talk when available\n"
    "- Pitfall or tradeoff: include important limitations, failure modes, or tradeoffs when available\n\n"
    "Create 3 to 6 topic sections when the transcript supports it.\n\n"
    "## Actionable Notes\n\n"
    "- 4 to 8 concrete actions, experiments, checks, or habits the reader can apply\n\n"
    "## Open Questions\n\n"
    "- 2 to 5 follow-up questions, uncertainties, or areas worth exploring further\n"
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
