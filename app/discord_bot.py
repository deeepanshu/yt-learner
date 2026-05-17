from __future__ import annotations

import argparse
import logging
import re

import discord
from discord import app_commands

from app.config import Settings, load_settings
from app.extractor import LearningExtractor
from app.job_queue import JobQueue
from app.pipeline import VideoProcessor
from app.storage import OutputStore
from app.telemetry import NoopTelemetry, configure_telemetry
from app.youtube_urls import InvalidYouTubeUrl, parse_youtube_url
YOUTUBE_URL_PATTERN = re.compile(r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)/\S+")


class LearnerBot(discord.Client):
    def __init__(self, *, settings: Settings, queue: JobQueue, telemetry=None) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.settings = settings
        self.queue = queue
        self.telemetry = telemetry or NoopTelemetry()
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        @self.tree.command(name="learn", description="Process a YouTube video into learning notes")
        @app_commands.describe(url="A YouTube video URL")
        async def learn(interaction: discord.Interaction, url: str) -> None:
            if not self._is_allowed_interaction(interaction):
                await interaction.response.send_message(
                    "This bot only accepts requests from the server.",
                    ephemeral=True,
                )
                return
            if not self._is_allowed_location(interaction.channel):
                await interaction.response.send_message(
                    "This bot is not enabled in this channel.",
                    ephemeral=True,
                )
                return

            try:
                parsed = parse_youtube_url(url)
            except InvalidYouTubeUrl:
                await interaction.response.send_message(
                    "I could not find a supported YouTube URL in that message.",
                    ephemeral=True,
                )
                return

            job = self._enqueue_job(
                video_url=parsed.canonical_url,
                requested_by=str(interaction.user.id),
                source="discord_slash_command",
                reply_channel_id=getattr(interaction.channel, "id", None),
            )
            await interaction.response.send_message(self._queued_text(job.id, parsed.canonical_url))

        await self.tree.sync()

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if not self._is_allowed_message(message):
            return
        if not self._is_allowed_location(message.channel):
            return
        matched_url = extract_youtube_url(message.content)
        if matched_url is None:
            return

        try:
            parsed = parse_youtube_url(matched_url)
        except InvalidYouTubeUrl:
            await message.channel.send("I could not find a supported YouTube URL in that message.")
            return

        job = self._enqueue_job(
            video_url=parsed.canonical_url,
            requested_by=str(message.author.id),
            source="discord_message",
            reply_channel_id=getattr(message.channel, "id", None),
        )
        await message.channel.send(self._queued_text(job.id, parsed.canonical_url))

    def _is_allowed_interaction(self, interaction: discord.Interaction) -> bool:
        return interaction.guild_id is not None

    def _is_allowed_message(self, message: discord.Message) -> bool:
        return message.guild is not None

    def _is_allowed_location(self, channel: discord.abc.Messageable) -> bool:
        channel_id = getattr(channel, "id", None)
        if self.settings.allowed_channel_id:
            return str(channel_id) == self.settings.allowed_channel_id
        return True

    def _enqueue_job(
        self,
        *,
        video_url: str,
        requested_by: str,
        source: str,
        reply_channel_id: int | None,
    ) -> object:
        job = self.queue.enqueue_summarize_video(
            video_url=video_url,
            requested_by=requested_by,
            source=source,
            reply_channel_id=reply_channel_id,
        )
        self.telemetry.record_job_enqueued(source=source)
        return job

    def _queued_text(self, job_id: int, url: str) -> str:
        return f"Queued job #{job_id} for {url}"


def build_processor(settings: Settings) -> VideoProcessor:
    store = OutputStore(settings.discord_output_dir, settings.db_path)
    extractor = LearningExtractor(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        max_transcript_chars=settings.max_transcript_chars,
    )
    return VideoProcessor(store=store, extractor=extractor)


def build_bot(settings: Settings, telemetry=None) -> LearnerBot:
    queue = JobQueue(settings.db_path)
    return LearnerBot(settings=settings, queue=queue, telemetry=telemetry)


def extract_youtube_url(message_content: str) -> str | None:
    match = YOUTUBE_URL_PATTERN.search(message_content)
    if match is None:
        return None
    return match.group(0).rstrip(")")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the yt-learner Discord bot.")
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate required environment variables and exit.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO)
    settings = load_settings()
    if args.check_config:
        print("Configuration looks valid.")
        return 0

    bot = build_bot(settings, configure_telemetry("yt-learner-discord"))
    bot.run(settings.discord_bot_token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
