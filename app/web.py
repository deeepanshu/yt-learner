from __future__ import annotations

import argparse
import html
import logging
from collections.abc import Callable
from urllib.parse import quote_plus

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

from app.channel_watches import WatchRepository, WatchedChannel
from app.config import Settings, load_settings
from app.job_queue import JobQueue
from app.telemetry import configure_logging
from app.youtube_channels import ResolvedYouTubeChannel, YouTubeChannelError, resolve_youtube_channel
from app.youtube_urls import InvalidYouTubeUrl, parse_youtube_url_or_id

LOGGER = logging.getLogger(__name__)
ChannelResolver = Callable[[str], ResolvedYouTubeChannel]
UI_PREFIX = "/ui"


class WatchWeb:
    def __init__(
        self,
        *,
        watch_repository: WatchRepository,
        job_queue: JobQueue,
        resolve_channel: ChannelResolver = resolve_youtube_channel,
    ) -> None:
        self.watch_repository = watch_repository
        self.job_queue = job_queue
        self.resolve_channel = resolve_channel

    async def home(self, request: Request) -> HTMLResponse:
        message = request.query_params.get("message")
        error = request.query_params.get("error")
        watches = self.watch_repository.list_subscriptions(active_only=True)
        return HTMLResponse(self._render_page(watches, message=message, error=error))

    async def add_watch(self, request: Request) -> Response:
        form = await request.form()
        raw = str(form.get("channel") or "").strip()
        if not raw:
            return self._redirect(error="Paste a YouTube channel URL, @handle, or channel ID.")
        try:
            resolved = self.resolve_channel(raw)
        except YouTubeChannelError:
            LOGGER.exception("watch_ui_resolve_failed raw_channel_ref=%r", raw)
            return self._redirect(error="I could not resolve that YouTube channel.")
        subscription = self.watch_repository.add_or_update_subscription(
            youtube_channel_id=resolved.channel_id,
            youtube_channel_ref=resolved.canonical_url,
            youtube_channel_title=resolved.title,
        )
        LOGGER.info(
            "watch_ui_saved subscription_id=%s youtube_channel_id=%s youtube_channel_title=%r",
            subscription.id,
            subscription.youtube_channel_id,
            subscription.youtube_channel_title,
        )
        return self._redirect(message=f"Watching {subscription.youtube_channel_title}.")

    async def learn_video(self, request: Request) -> Response:
        form = await request.form()
        raw = str(form.get("url") or "").strip()
        if not raw:
            return self._redirect(error="Paste a YouTube video URL or 11-character id.")
        try:
            parsed = parse_youtube_url_or_id(raw)
        except InvalidYouTubeUrl:
            return self._redirect(error="I could not parse that YouTube URL.")
        job = self.job_queue.enqueue_summarize_video(
            video_url=parsed.canonical_url,
            requested_by="ui",
            source="ui_learn",
        )
        LOGGER.info(
            "watch_ui_learn_queued job_id=%s video_id=%s canonical_url=%s",
            job.id,
            parsed.video_id,
            parsed.canonical_url,
        )
        return self._redirect(
            message=f"Queued job #{job.id} for {parsed.canonical_url}. Worker will call Ollama and write to Outline."
        )

    async def delete_watch(self, request: Request) -> Response:
        subscription_id = int(request.path_params["subscription_id"])
        removed = self.watch_repository.deactivate_subscription_by_id(subscription_id=subscription_id)
        if removed is None:
            return self._redirect(error="That watch is already gone.")
        LOGGER.info(
            "watch_ui_removed subscription_id=%s youtube_channel_id=%s",
            removed.id,
            removed.youtube_channel_id,
        )
        return self._redirect(message=f"Stopped watching {removed.youtube_channel_title}.")

    def _redirect(self, *, message: str | None = None, error: str | None = None) -> RedirectResponse:
        if error:
            return RedirectResponse(f"{UI_PREFIX}/?error={quote_plus(error)}", status_code=303)
        if message:
            return RedirectResponse(f"{UI_PREFIX}/?message={quote_plus(message)}", status_code=303)
        return RedirectResponse(f"{UI_PREFIX}/", status_code=303)

    def _render_page(
        self,
        watches: list[WatchedChannel],
        *,
        message: str | None,
        error: str | None,
    ) -> str:
        rows = []
        for watch in watches:
            status = "bootstrapped" if watch.bootstrap_completed_at else "next poll is bootstrap-only"
            rows.append(
                f"""
                <tr>
                  <td><a href="{html.escape(watch.youtube_channel_ref, quote=True)}">{html.escape(watch.youtube_channel_title)}</a></td>
                  <td><code>{html.escape(watch.youtube_channel_id)}</code></td>
                  <td>{html.escape(status)}</td>
                  <td>
                    <form method="post" action="{UI_PREFIX}/watches/{watch.id}/delete">
                      <button type="submit">Remove</button>
                    </form>
                  </td>
                </tr>
                """
            )
        table = (
            "<p>No watched channels yet.</p>"
            if not rows
            else f"""
            <table>
              <thead>
                <tr><th>Channel</th><th>ID</th><th>Status</th><th></th></tr>
              </thead>
              <tbody>
                {''.join(rows)}
              </tbody>
            </table>
            """
        )
        banner = ""
        if message:
            banner += f'<p class="ok">{html.escape(message)}</p>'
        if error:
            banner += f'<p class="err">{html.escape(error)}</p>'
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>yt-learner watches</title>
  <style>
    :root {{ color-scheme: light dark; }}
    body {{ font: 16px/1.4 system-ui, sans-serif; margin: 2rem auto; max-width: 52rem; padding: 0 1rem; }}
    form.inline {{ display: flex; gap: .5rem; flex-wrap: wrap; margin: 1rem 0 2rem; }}
    input[name="channel"] {{ flex: 1 1 16rem; padding: .4rem .5rem; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; padding: .4rem .3rem; border-bottom: 1px solid #8884; vertical-align: top; }}
    .ok {{ color: #0a7; }}
    .err {{ color: #c40; }}
    code {{ font-size: .9em; }}
    .hint {{ color: #888; }}
  </style>
</head>
<body>
  <h1>yt-learner watches</h1>
  <p class="hint">New uploads are learned on the daily scheduler and saved to Outline. The first poll after adding a channel records the feed and does not backfill. Learn queues one video now.</p>
  {banner}
  <form class="inline" method="post" action="{UI_PREFIX}/learn">
    <label for="url">Learn video</label>
    <input id="url" name="url" required placeholder="https://www.youtube.com/watch?v=… or video id" autocomplete="off">
    <button type="submit">Learn</button>
  </form>
  <form class="inline" method="post" action="{UI_PREFIX}/watches">
    <label for="channel">YouTube channel</label>
    <input id="channel" name="channel" required placeholder="@handle, channel URL, or UC… id" autocomplete="off">
    <button type="submit">Watch</button>
  </form>
  {table}
</body>
</html>
"""

async def redirect_root(_request: Request) -> RedirectResponse:
    return RedirectResponse(url=f"{UI_PREFIX}/", status_code=303)


def create_app(
    *,
    settings: Settings | None = None,
    watch_repository: WatchRepository | None = None,
    job_queue: JobQueue | None = None,
    resolve_channel: ChannelResolver = resolve_youtube_channel,
) -> Starlette:
    loaded = settings or load_settings()
    repository = watch_repository or WatchRepository(loaded.database_url)
    queue = job_queue or JobQueue(loaded.database_url)
    web = WatchWeb(watch_repository=repository, job_queue=queue, resolve_channel=resolve_channel)
    return Starlette(
        routes=[
            Route("/", redirect_root, methods=["GET"]),
            Route(UI_PREFIX, web.home, methods=["GET"]),
            Route(f"{UI_PREFIX}/", web.home, methods=["GET"]),
            Route(f"{UI_PREFIX}/learn", web.learn_video, methods=["POST"]),
            Route(f"{UI_PREFIX}/watches", web.add_watch, methods=["POST"]),
            Route(f"{UI_PREFIX}/watches/{{subscription_id:int}}/delete", web.delete_watch, methods=["POST"]),
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the yt-learner watch UI.")
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate required environment variables and exit.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging("yt-learner-web")
    settings = load_settings()
    if args.check_config:
        print("Configuration looks valid.")
        return 0
    app = create_app(settings=settings)
    uvicorn.run(app, host=settings.watch_ui_host, port=settings.watch_ui_port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
