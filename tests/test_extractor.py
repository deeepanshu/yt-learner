from collections.abc import Mapping
from typing import cast

from app.extractor import ExtractionInput, SYSTEM_PROMPT, build_messages
from app.transcript import TranscriptData, TranscriptSegment


def message_content(message: object) -> str:
    content = cast(Mapping[str, object], message)["content"]
    assert isinstance(content, str)
    return content


def test_build_messages_uses_expected_structure() -> None:
    payload = ExtractionInput(
        title="Video Title",
        url="https://www.youtube.com/watch?v=abc123xyz",
        transcript=TranscriptData(
            segments=[
                TranscriptSegment(start_seconds=0, text="first line"),
                TranscriptSegment(start_seconds=10, text="second line"),
            ]
        ),
    )

    messages = build_messages(
        payload=payload,
        processed_at="2026-05-17T00:00:00+00:00",
        max_transcript_chars=None,
    )

    assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
    content = message_content(messages[1])
    assert "Video title: Video Title" in content
    assert "Processed timestamp: 2026-05-17T00:00:00+00:00" in content
    assert "first line\nsecond line" in content
    assert "Additional user request:" not in content


def test_build_messages_includes_extra_prompt() -> None:
    payload = ExtractionInput(
        title="Video Title",
        url="https://www.youtube.com/watch?v=abc123xyz",
        transcript=TranscriptData(segments=[TranscriptSegment(start_seconds=0, text="transcript")]),
        extra_prompt="focus on deployment advice",
    )

    messages = build_messages(
        payload=payload,
        processed_at="2026-05-17T00:00:00+00:00",
        max_transcript_chars=None,
    )

    content = message_content(messages[1])
    assert "Additional user request:\nfocus on deployment advice" in content
    assert "only include information supported by the transcript" in content


def test_build_messages_truncates_transcript() -> None:
    payload = ExtractionInput(
        title="Video Title",
        url="https://www.youtube.com/watch?v=abc123xyz",
        transcript=TranscriptData(segments=[TranscriptSegment(start_seconds=0, text="abcdef")]),
    )

    messages = build_messages(
        payload=payload,
        processed_at="2026-05-17T00:00:00+00:00",
        max_transcript_chars=3,
    )

    assert message_content(messages[1]).endswith("abc")
