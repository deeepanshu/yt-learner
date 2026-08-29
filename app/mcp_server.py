from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass

from mcp.server import MCPServer
from mcp.server.auth.provider import TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import AnyHttpUrl

from app.mcp_auth import CloudflareAccessSettings, CloudflareAccessTokenVerifier
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


def create_mcp_server(
    *,
    auth_settings: AuthSettings | None = None,
    token_verifier: TokenVerifier | None = None,
) -> MCPServer:
    server = MCPServer(
        "yt-learner",
        version="0.1.0",
        instructions="Fetch English transcripts from YouTube videos.",
        auth=auth_settings,
        token_verifier=token_verifier,
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


def create_http_mcp(settings: CloudflareAccessSettings) -> MCPServer:
    auth_settings = AuthSettings(
        issuer_url=AnyHttpUrl(settings.issuer_url),
        resource_server_url=AnyHttpUrl(settings.public_url),
        required_scopes=settings.required_scopes,
    )
    return create_mcp_server(
        auth_settings=auth_settings,
        token_verifier=CloudflareAccessTokenVerifier(settings),
    )


mcp = create_mcp_server()


def main() -> None:
    mcp.run()


def http_main() -> None:
    settings = CloudflareAccessSettings.from_environment()
    create_http_mcp(settings).run(transport="streamable-http", host="0.0.0.0", port=settings.port, streamable_http_path=settings.path)


if __name__ == "__main__":
    if "--http" in sys.argv[1:]:
        http_main()
    else:
        main()
