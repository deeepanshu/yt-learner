from app.extractor import ExtractionInput, SYSTEM_PROMPT, build_messages
from app.transcript import TranscriptData, TranscriptSegment


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
    assert "Video title: Video Title" in messages[1]["content"]
    assert "Processed timestamp: 2026-05-17T00:00:00+00:00" in messages[1]["content"]
    assert "first line\nsecond line" in messages[1]["content"]


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

    assert messages[1]["content"].endswith("abc")
