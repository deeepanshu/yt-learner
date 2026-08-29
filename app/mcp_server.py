from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from app.transcript import TranscriptData, TranscriptError, TranscriptSegment, fetch_transcript
from app.youtube_urls import InvalidYouTubeUrl, parse_youtube_url_or_id


@dataclass(frozen=True)
class YoutubeTranscript:
    video_id: str
    url: str
    text: str
    segments: list[TranscriptSegment]


def load_youtube_transcript(
    url: str,
    *,
    transcript_fetcher: Callable[[str], TranscriptData] | None = None,
) -> YoutubeTranscript:
    parsed = parse_youtube_url_or_id(url)
    fetcher = transcript_fetcher if transcript_fetcher is not None else fetch_transcript
    data = fetcher(parsed.video_id)
    return YoutubeTranscript(
        video_id=parsed.video_id,
        url=parsed.canonical_url,
        text=data.text,
        segments=data.segments,
    )


def create_mcp_server() -> MCPServer:
    server = MCPServer(
        "yt-learner",
        version="0.1.0",
        instructions="Fetch English transcripts from YouTube videos.",
    )

    @server.tool(
        title="Get YouTube transcript",
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
    )
    def get_youtube_transcript(url: str) -> YoutubeTranscript:
        """Fetch the English transcript for a YouTube video.

        Accepts a watch, shorts, embed, or youtu.be URL, or an 11-character video ID.
        """
        try:
            return load_youtube_transcript(url)
        except (InvalidYouTubeUrl, TranscriptError) as exc:
            raise ToolError(str(exc)) from exc

    return server


def _http_port() -> int:
    raw = os.getenv("MCP_PORT", "3003")
    try:
        port = int(raw)
    except ValueError as exc:
        raise RuntimeError("Environment variable MCP_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError("Environment variable MCP_PORT must be between 1 and 65535")
    return port


def _http_path() -> str:
    path = os.getenv("MCP_PATH", "/mcp").strip().rstrip("/")
    if not path.startswith("/"):
        raise RuntimeError("Environment variable MCP_PATH must start with /")
    return path


mcp = create_mcp_server()


def main() -> None:
    mcp.run()


def http_main() -> None:
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=_http_port(),
        streamable_http_path=_http_path(),
    )


if __name__ == "__main__":
    if "--http" in sys.argv[1:]:
        http_main()
    else:
        main()
