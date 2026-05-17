from __future__ import annotations

import argparse
import logging
import re

import discord
from discord import app_commands

from app.channel_watches import WatchRepository
from app.config import Settings, load_settings
from app.extractor import LearningExtractor
from app.job_queue import JobQueue
from app.pipeline import VideoProcessor
from app.storage import OutputStore
from app.telemetry import NoopTelemetry, configure_logging, configure_telemetry
from app.youtube_channels import YouTubeChannelError, resolve_youtube_channel
from app.youtube_urls import InvalidYouTubeUrl, parse_youtube_url

YOUTUBE_URL_PATTERN = re.compile(r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)/\S+")
LOGGER = logging.getLogger(__name__)


class LearnerBot(discord.Client):
    def __init__(
        self,
        *,
        settings: Settings,
        queue: JobQueue,
        watch_repository: WatchRepository,
        telemetry=None,
    ) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.settings = settings
        self.queue = queue
        self.watch_repository = watch_repository
        self.telemetry = telemetry or NoopTelemetry()
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        @self.tree.command(name="learn", description="Process a YouTube video into learning notes")
        @app_commands.describe(url="A YouTube video URL")
        async def learn(interaction: discord.Interaction, url: str) -> None:
            LOGGER.info(
                "discord_command_received command=learn guild_id=%s channel_id=%s user_id=%s raw_url=%r",
                interaction.guild_id,
                getattr(interaction.channel, "id", None),
                getattr(interaction.user, "id", None),
                url,
            )
            if not self._is_allowed_interaction(interaction):
                LOGGER.info(
                    "discord_command_rejected command=learn reason=not_in_guild guild_id=%s user_id=%s",
                    interaction.guild_id,
                    getattr(interaction.user, "id", None),
                )
                await interaction.response.send_message(
                    "This bot only accepts requests from the server.",
                    ephemeral=True,
                )
                return
            if not self._is_allowed_location(interaction.channel):
                LOGGER.info(
                    "discord_command_rejected command=learn reason=channel_not_allowed guild_id=%s channel_id=%s user_id=%s",
                    interaction.guild_id,
                    getattr(interaction.channel, "id", None),
                    getattr(interaction.user, "id", None),
                )
                await interaction.response.send_message(
                    "This bot is not enabled in this channel.",
                    ephemeral=True,
                )
                return

            try:
                parsed = parse_youtube_url(url)
            except InvalidYouTubeUrl:
                LOGGER.info(
                    "discord_command_parse_failed command=learn guild_id=%s user_id=%s raw_url=%r",
                    interaction.guild_id,
                    getattr(interaction.user, "id", None),
                    url,
                )
                await interaction.response.send_message(
                    "I could not find a supported YouTube URL in that message.",
                    ephemeral=True,
                )
                return
            LOGGER.info(
                "discord_command_parsed command=learn guild_id=%s channel_id=%s user_id=%s video_id=%s canonical_url=%s",
                interaction.guild_id,
                getattr(interaction.channel, "id", None),
                getattr(interaction.user, "id", None),
                parsed.video_id,
                parsed.canonical_url,
            )

            job = self._enqueue_job(
                video_url=parsed.canonical_url,
                requested_by=str(interaction.user.id),
                source="discord_slash_command",
                reply_channel_id=getattr(interaction.channel, "id", None),
            )
            await interaction.response.send_message(self._queued_text(job.id, parsed.canonical_url))

        watch_group = app_commands.Group(name="watch", description="Manage watched YouTube channels")

        @watch_group.command(name="add", description="Watch a YouTube channel and route uploads to a Discord channel")
        @app_commands.describe(
            youtube_channel="A YouTube channel URL, handle, or channel ID",
            discord_channel="The Discord channel that should receive learned notes",
        )
        async def watch_add(
            interaction: discord.Interaction,
            youtube_channel: str,
            discord_channel: discord.TextChannel,
        ) -> None:
            LOGGER.info(
                "discord_command_received command=watch_add guild_id=%s channel_id=%s user_id=%s raw_channel_ref=%r target_discord_channel_id=%s",
                interaction.guild_id,
                getattr(interaction.channel, "id", None),
                getattr(interaction.user, "id", None),
                youtube_channel,
                getattr(discord_channel, "id", None),
            )
            if not self._is_allowed_interaction(interaction):
                LOGGER.info(
                    "discord_command_rejected command=watch_add reason=not_in_guild guild_id=%s user_id=%s",
                    interaction.guild_id,
                    getattr(interaction.user, "id", None),
                )
                await interaction.response.send_message(
                    "This bot only accepts requests from the server.",
                    ephemeral=True,
                )
                return
            if not self._is_admin_interaction(interaction):
                LOGGER.info(
                    "discord_command_rejected command=watch_add reason=missing_manage_guild guild_id=%s user_id=%s",
                    interaction.guild_id,
                    getattr(interaction.user, "id", None),
                )
                await interaction.response.send_message(
                    "You need server management permissions to manage watched channels.",
                    ephemeral=True,
                )
                return
            await interaction.response.defer(thinking=True, ephemeral=True)
            try:
                resolved = resolve_youtube_channel(youtube_channel)
            except YouTubeChannelError:
                LOGGER.exception(
                    "discord_command_parse_failed command=watch_add guild_id=%s user_id=%s raw_channel_ref=%r",
                    interaction.guild_id,
                    getattr(interaction.user, "id", None),
                    youtube_channel,
                )
                await interaction.followup.send(
                    "I could not resolve that YouTube channel.",
                    ephemeral=True,
                )
                return
            LOGGER.info(
                "discord_command_parsed command=watch_add guild_id=%s user_id=%s raw_channel_ref=%r youtube_channel_id=%s canonical_url=%s youtube_channel_title=%r target_discord_channel_id=%s",
                interaction.guild_id,
                getattr(interaction.user, "id", None),
                youtube_channel,
                resolved.channel_id,
                resolved.canonical_url,
                resolved.title,
                getattr(discord_channel, "id", None),
            )
            subscription = self.watch_repository.add_or_update_subscription(
                guild_id=str(interaction.guild_id),
                youtube_channel_id=resolved.channel_id,
                youtube_channel_ref=resolved.canonical_url,
                youtube_channel_title=resolved.title,
                discord_channel_id=discord_channel.id,
            )
            LOGGER.info(
                "watch_subscription_saved guild_id=%s subscription_id=%s youtube_channel_id=%s youtube_channel_title=%r discord_channel_id=%s",
                interaction.guild_id,
                subscription.id,
                subscription.youtube_channel_id,
                subscription.youtube_channel_title,
                subscription.discord_channel_id,
            )
            await interaction.followup.send(
                f"Watching {subscription.youtube_channel_title} and routing new uploads to <#{subscription.discord_channel_id}>."
            )

        @watch_group.command(name="list", description="List watched YouTube channels for this server")
        async def watch_list(interaction: discord.Interaction) -> None:
            LOGGER.info(
                "discord_command_received command=watch_list guild_id=%s channel_id=%s user_id=%s",
                interaction.guild_id,
                getattr(interaction.channel, "id", None),
                getattr(interaction.user, "id", None),
            )
            if not self._is_allowed_interaction(interaction):
                await interaction.response.send_message(
                    "This bot only accepts requests from the server.",
                    ephemeral=True,
                )
                return
            if not self._is_admin_interaction(interaction):
                await interaction.response.send_message(
                    "You need server management permissions to manage watched channels.",
                    ephemeral=True,
                )
                return
            subscriptions = self.watch_repository.list_subscriptions(guild_id=str(interaction.guild_id))
            LOGGER.info(
                "watch_list_loaded guild_id=%s user_id=%s count=%s",
                interaction.guild_id,
                getattr(interaction.user, "id", None),
                len(subscriptions),
            )
            if not subscriptions:
                await interaction.response.send_message("No watched YouTube channels are configured yet.")
                return
            await interaction.response.send_message(self._format_subscription_list(subscriptions))

        @watch_group.command(name="remove", description="Stop watching a YouTube channel")
        @app_commands.describe(youtube_channel_or_watch_id="A watch ID, channel URL, handle, or channel ID")
        async def watch_remove(interaction: discord.Interaction, youtube_channel_or_watch_id: str) -> None:
            LOGGER.info(
                "discord_command_received command=watch_remove guild_id=%s channel_id=%s user_id=%s raw_reference=%r",
                interaction.guild_id,
                getattr(interaction.channel, "id", None),
                getattr(interaction.user, "id", None),
                youtube_channel_or_watch_id,
            )
            if not self._is_allowed_interaction(interaction):
                await interaction.response.send_message(
                    "This bot only accepts requests from the server.",
                    ephemeral=True,
                )
                return
            if not self._is_admin_interaction(interaction):
                await interaction.response.send_message(
                    "You need server management permissions to manage watched channels.",
                    ephemeral=True,
                )
                return

            removed = self._remove_subscription(
                guild_id=str(interaction.guild_id),
                raw_reference=youtube_channel_or_watch_id,
            )
            if removed is None:
                LOGGER.info(
                    "watch_remove_not_found guild_id=%s user_id=%s raw_reference=%r",
                    interaction.guild_id,
                    getattr(interaction.user, "id", None),
                    youtube_channel_or_watch_id,
                )
                await interaction.response.send_message(
                    "I could not find an active watched channel matching that value.",
                    ephemeral=True,
                )
                return
            LOGGER.info(
                "watch_subscription_removed guild_id=%s user_id=%s subscription_id=%s youtube_channel_id=%s youtube_channel_title=%r",
                interaction.guild_id,
                getattr(interaction.user, "id", None),
                removed.id,
                removed.youtube_channel_id,
                removed.youtube_channel_title,
            )
            await interaction.response.send_message(f"Stopped watching {removed.youtube_channel_title}.")

        self.tree.add_command(watch_group)
        await self.tree.sync()

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        LOGGER.info(
            "discord_message_received guild_id=%s channel_id=%s user_id=%s content_preview=%r",
            getattr(message.guild, "id", None),
            getattr(message.channel, "id", None),
            getattr(message.author, "id", None),
            _preview_text(message.content),
        )
        if not self._is_allowed_message(message):
            LOGGER.info(
                "discord_message_ignored reason=not_in_guild user_id=%s content_preview=%r",
                getattr(message.author, "id", None),
                _preview_text(message.content),
            )
            return
        if not self._is_allowed_location(message.channel):
            LOGGER.info(
                "discord_message_ignored reason=channel_not_allowed guild_id=%s channel_id=%s user_id=%s",
                getattr(message.guild, "id", None),
                getattr(message.channel, "id", None),
                getattr(message.author, "id", None),
            )
            return
        matched_url = extract_youtube_url(message.content)
        if matched_url is None:
            LOGGER.info(
                "discord_message_ignored reason=no_youtube_url guild_id=%s channel_id=%s user_id=%s",
                getattr(message.guild, "id", None),
                getattr(message.channel, "id", None),
                getattr(message.author, "id", None),
            )
            return
        LOGGER.info(
            "discord_message_matched_url guild_id=%s channel_id=%s user_id=%s matched_url=%r",
            getattr(message.guild, "id", None),
            getattr(message.channel, "id", None),
            getattr(message.author, "id", None),
            matched_url,
        )

        try:
            parsed = parse_youtube_url(matched_url)
        except InvalidYouTubeUrl:
            LOGGER.info(
                "discord_message_parse_failed guild_id=%s channel_id=%s user_id=%s matched_url=%r",
                getattr(message.guild, "id", None),
                getattr(message.channel, "id", None),
                getattr(message.author, "id", None),
                matched_url,
            )
            await message.channel.send("I could not find a supported YouTube URL in that message.")
            return
        LOGGER.info(
            "discord_message_parsed guild_id=%s channel_id=%s user_id=%s video_id=%s canonical_url=%s",
            getattr(message.guild, "id", None),
            getattr(message.channel, "id", None),
            getattr(message.author, "id", None),
            parsed.video_id,
            parsed.canonical_url,
        )

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

    def _is_admin_interaction(self, interaction: discord.Interaction) -> bool:
        permissions = getattr(interaction.user, "guild_permissions", None)
        return bool(getattr(permissions, "manage_guild", False))

    def _is_allowed_location(self, channel: discord.abc.Messageable) -> bool:
        channel_id = getattr(channel, "id", None)
        if self.settings.allowed_channel_id:
            return str(channel_id) == self.settings.allowed_channel_id
        return True

    def _remove_subscription(self, *, guild_id: str, raw_reference: str):
        cleaned = raw_reference.strip()
        if cleaned.isdigit():
            return self.watch_repository.deactivate_subscription_by_id(
                guild_id=guild_id,
                subscription_id=int(cleaned),
            )
        try:
            resolved = resolve_youtube_channel(cleaned)
        except YouTubeChannelError:
            return None
        return self.watch_repository.deactivate_subscription_by_channel_id(
            guild_id=guild_id,
            youtube_channel_id=resolved.channel_id,
        )

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
        LOGGER.info(
            "job_enqueued job_id=%s source=%s requested_by=%s reply_channel_id=%s video_url=%s",
            job.id,
            source,
            requested_by,
            reply_channel_id,
            video_url,
        )
        self.telemetry.record_job_enqueued(source=source)
        return job

    def _queued_text(self, job_id: int, url: str) -> str:
        return f"Queued job #{job_id} for {url}"

    def _format_subscription_list(self, subscriptions) -> str:
        return "\n".join(
            f"#{subscription.id} {subscription.youtube_channel_title} -> <#{subscription.discord_channel_id}>"
            for subscription in subscriptions
        )


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
    watch_repository = WatchRepository(settings.db_path)
    return LearnerBot(settings=settings, queue=queue, watch_repository=watch_repository, telemetry=telemetry)


def extract_youtube_url(message_content: str) -> str | None:
    match = YOUTUBE_URL_PATTERN.search(message_content)
    if match is None:
        return None
    return match.group(0).rstrip(")")


def _preview_text(value: str, *, limit: int = 200) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit]}..."


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
    configure_logging("yt-learner-discord")
    settings = load_settings()
    if args.check_config:
        print("Configuration looks valid.")
        return 0

    bot = build_bot(settings, configure_telemetry("yt-learner-discord"))
    bot.run(settings.discord_bot_token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
