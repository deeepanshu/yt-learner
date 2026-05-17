from __future__ import annotations

import argparse
import logging
import re

import discord
from discord import app_commands

from app.config import Settings, load_settings
from app.extractor import ExtractionError, LearningExtractor
from app.pipeline import ProcessedVideo, VideoProcessor
from app.storage import OutputStore
from app.transcript import TranscriptFetchError, TranscriptUnavailableError, UnsupportedVideoError
from app.youtube_urls import InvalidYouTubeUrl

LOGGER = logging.getLogger(__name__)
YOUTUBE_URL_PATTERN = re.compile(r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)/\S+")


class LearnerBot(discord.Client):
    def __init__(self, *, settings: Settings, processor: VideoProcessor) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.settings = settings
        self.processor = processor
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        @self.tree.command(name="learn", description="Process a YouTube video into learning notes")
        @app_commands.describe(url="A YouTube video URL")
        async def learn(interaction: discord.Interaction, url: str) -> None:
            if not self._is_allowed_user(interaction.user.id):
                await interaction.response.send_message("Unauthorized.", ephemeral=True)
                return

            await interaction.response.defer(thinking=True)
            await self._process_and_respond(url=url, send=interaction.followup.send)

        await self.tree.sync()

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if not self._is_allowed_user(message.author.id):
            return
        if not self._is_allowed_location(message.channel):
            return
        matched_url = extract_youtube_url(message.content)
        if matched_url is None:
            return

        await message.channel.send("Processing your YouTube URL...")
        await self._process_and_respond(url=matched_url, send=message.channel.send)

    async def _process_and_respond(self, *, url: str, send) -> None:
        try:
            result = await self.processor.process_video(url, requested_by=self.settings.discord_allowed_user_id)
        except InvalidYouTubeUrl:
            await send("I could not find a supported YouTube URL in that message.")
            return
        except TranscriptUnavailableError:
            await send("I could not fetch an English transcript for this video.")
            return
        except TranscriptFetchError:
            await send("I could not fetch the transcript right now. Please try again later.")
            return
        except UnsupportedVideoError:
            await send("The video looks private, unavailable, or unsupported.")
            return
        except ExtractionError:
            LOGGER.exception("OpenAI extraction failure")
            await send("The extraction failed while calling OpenAI. The transcript was saved for debugging.")
            return
        except Exception:
            LOGGER.exception("Unhandled processing failure")
            await send("The extraction failed while calling OpenAI. Try again later.")
            return

        await send(
            content=self._completion_text(result),
            file=discord.File(result.output_path),
        )

    def _completion_text(self, result: ProcessedVideo) -> str:
        prefix = "Reused existing notes" if result.reused_existing else "Done"
        return f"{prefix}: {result.title}"

    def _is_allowed_user(self, user_id: int) -> bool:
        return str(user_id) == self.settings.discord_allowed_user_id

    def _is_allowed_location(self, channel: discord.abc.Messageable) -> bool:
        channel_id = getattr(channel, "id", None)
        if self.settings.allowed_channel_id:
            return str(channel_id) == self.settings.allowed_channel_id
        return True


def build_bot(settings: Settings) -> LearnerBot:
    store = OutputStore(settings.discord_output_dir)
    extractor = LearningExtractor(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        max_transcript_chars=settings.max_transcript_chars,
    )
    processor = VideoProcessor(store=store, extractor=extractor)
    return LearnerBot(settings=settings, processor=processor)


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

    bot = build_bot(settings)
    bot.run(settings.discord_bot_token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
