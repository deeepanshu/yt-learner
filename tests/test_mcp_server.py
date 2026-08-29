from __future__ import annotations

import asyncio

from mcp import Client

from app.mcp_server import load_youtube_transcript, mcp
from app.transcript import TranscriptData, TranscriptSegment, TranscriptUnavailableError
from app.youtube_urls import InvalidYouTubeUrl


def _transcript() -> TranscriptData:
    return TranscriptData(
        segments=[
            TranscriptSegment(start_seconds=0, text="first line"),
            TranscriptSegment(start_seconds=12, text="second line"),
        ]
    )


def test_load_youtube_transcript_from_url() -> None:
    result = load_youtube_transcript(
        "https://www.youtube.com/watch?v=abc123xyzab",
        transcript_fetcher=lambda video_id: _transcript(),
    )

    assert result.video_id == "abc123xyzab"
    assert result.url == "https://www.youtube.com/watch?v=abc123xyzab"
    assert result.text == "first line\nsecond line"
    assert result.segments[1].start_seconds == 12


def test_load_youtube_transcript_from_video_id() -> None:
    seen: list[str] = []

    def fetch(video_id: str) -> TranscriptData:
        seen.append(video_id)
        return _transcript()

    result = load_youtube_transcript("dQw4w9WgXcQ", transcript_fetcher=fetch)

    assert seen == ["dQw4w9WgXcQ"]
    assert result.video_id == "dQw4w9WgXcQ"
    assert result.url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_load_youtube_transcript_rejects_invalid_url() -> None:
    try:
        load_youtube_transcript("https://example.com/watch?v=abc123xyzab")
    except InvalidYouTubeUrl:
        return
    raise AssertionError("Expected InvalidYouTubeUrl")


def test_mcp_tool_returns_transcript(monkeypatch) -> None:
    monkeypatch.setattr("app.mcp_server.fetch_transcript", lambda video_id: _transcript())

    async def run() -> None:
        async with Client(mcp) as client:
            tools = await client.list_tools()
            assert [tool.name for tool in tools.tools] == ["get_youtube_transcript"]

            result = await client.call_tool(
                "get_youtube_transcript",
                {"url": "https://youtu.be/abc123xyzab"},
            )
            assert result.is_error is False
            assert result.structured_content is not None
            assert result.structured_content["video_id"] == "abc123xyzab"
            assert result.structured_content["text"] == "first line\nsecond line"
            assert result.structured_content["segments"][0]["start_seconds"] == 0

    asyncio.run(run())


def test_mcp_tool_reports_unavailable_transcript(monkeypatch) -> None:
    def fail(video_id: str) -> TranscriptData:
        raise TranscriptUnavailableError("No English transcript is available")

    monkeypatch.setattr("app.mcp_server.fetch_transcript", fail)

    async def run() -> None:
        async with Client(mcp) as client:
            result = await client.call_tool(
                "get_youtube_transcript",
                {"url": "https://www.youtube.com/watch?v=abc123xyzab"},
            )
            assert result.is_error is True
            assert "No English transcript is available" in result.content[0].text

    asyncio.run(run())
