from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from app.channel_watches import WatchRepository, WatchedChannel
from app.job_queue import JobQueue
from app.storage import OutputStore
from app.youtube_channels import ChannelFeedVideo, YouTubeChannelError, fetch_channel_feed, fetch_channel_feeds

LOGGER = logging.getLogger(__name__)
SCHEDULER_REQUESTED_BY = "youtube-channel-scheduler"
SCHEDULER_SOURCE = "youtube_channel_scheduler"
Feed = tuple[str, list[ChannelFeedVideo]]
FeedFetcher = Callable[[str], Feed]
BatchFeedFetcher = Callable[[list[str]], dict[str, Feed]]


@dataclass(frozen=True)
class SchedulerPollResult:
    subscriptions_polled: int = 0
    videos_seen: int = 0
    jobs_enqueued: int = 0


class ChannelScheduler:
    def __init__(
        self,
        *,
        watch_repository: WatchRepository,
        queue: JobQueue,
        store: OutputStore,
        feed_fetcher: FeedFetcher = fetch_channel_feed,
        batch_feed_fetcher: BatchFeedFetcher | None = None,
    ) -> None:
        self.watch_repository = watch_repository
        self.queue = queue
        self.store = store
        self.feed_fetcher = feed_fetcher
        self.batch_feed_fetcher = batch_feed_fetcher

    async def poll_once(self) -> SchedulerPollResult:
        result = SchedulerPollResult()
        subscriptions = self.watch_repository.get_active_subscriptions()
        LOGGER.info("scheduler_poll_started subscription_count=%s", len(subscriptions))
        feeds_by_channel = self._fetch_feeds(subscriptions)
        for subscription in subscriptions:
            feed = feeds_by_channel.get(subscription.youtube_channel_id)
            if feed is None:
                continue
            _, videos = feed
            result = self._poll_subscription(subscription, videos, result)
        LOGGER.info(
            "scheduler_poll_finished subscriptions_polled=%s videos_seen=%s jobs_enqueued=%s",
            result.subscriptions_polled,
            result.videos_seen,
            result.jobs_enqueued,
        )
        return result

    def _fetch_feeds(self, subscriptions: list[WatchedChannel]) -> dict[str, Feed]:
        channel_ids = [subscription.youtube_channel_id for subscription in subscriptions]
        if self.batch_feed_fetcher is not None:
            try:
                return self.batch_feed_fetcher(channel_ids)
            except YouTubeChannelError:
                LOGGER.exception("Unable to poll watched YouTube channels")
                return {}

        feeds: dict[str, Feed] = {}
        for subscription in subscriptions:
            try:
                feeds[subscription.youtube_channel_id] = self.feed_fetcher(subscription.youtube_channel_id)
            except YouTubeChannelError:
                LOGGER.exception(
                    "Unable to poll watched YouTube channel %s",
                    subscription.youtube_channel_id,
                )
        return feeds

    def _poll_subscription(
        self,
        subscription: WatchedChannel,
        videos: list[ChannelFeedVideo],
        current: SchedulerPollResult,
    ) -> SchedulerPollResult:
        seen = current.videos_seen
        enqueued = current.jobs_enqueued

        if subscription.bootstrap_completed_at is None:
            LOGGER.info(
                "scheduler_subscription_bootstrap_started subscription_id=%s youtube_channel_id=%s initial_video_count=%s",
                subscription.id,
                subscription.youtube_channel_id,
                len(videos),
            )
            for video in videos:
                if self.watch_repository.record_discovered_video(
                    subscription_id=subscription.id,
                    video_id=video.video_id,
                    video_url=video.video_url,
                    title=video.title,
                    published_at=video.published_at,
                ):
                    seen += 1
            self.watch_repository.mark_bootstrap_complete(subscription.id)
            LOGGER.info(
                "scheduler_subscription_bootstrap_completed subscription_id=%s youtube_channel_id=%s recorded_videos=%s",
                subscription.id,
                subscription.youtube_channel_id,
                seen - current.videos_seen,
            )
            return SchedulerPollResult(
                subscriptions_polled=current.subscriptions_polled + 1,
                videos_seen=seen,
                jobs_enqueued=enqueued,
            )

        for video in reversed(videos):
            if not self.watch_repository.record_discovered_video(
                subscription_id=subscription.id,
                video_id=video.video_id,
                video_url=video.video_url,
                title=video.title,
                published_at=video.published_at,
            ):
                continue
            LOGGER.info(
                "scheduler_video_discovered subscription_id=%s youtube_channel_id=%s video_id=%s title=%r",
                subscription.id,
                subscription.youtube_channel_id,
                video.video_id,
                video.title,
            )
            seen += 1
            existing = self.store.find_existing_learning_record(
                source_type="youtube_url",
                source_key=video.video_id,
            )
            if existing is not None:
                LOGGER.info(
                    "scheduler_video_skipped_existing_learning subscription_id=%s video_id=%s learning_record_id=%s",
                    subscription.id,
                    video.video_id,
                    existing.id,
                )
                self.watch_repository.mark_video_existing_learning(
                    subscription_id=subscription.id,
                    video_id=video.video_id,
                    learning_record_id=existing.id,
                )
                continue

            job = self.queue.enqueue_summarize_video(
                video_url=video.video_url,
                youtube_channel_id=subscription.youtube_channel_id,
                requested_by=SCHEDULER_REQUESTED_BY,
                source=SCHEDULER_SOURCE,
            )
            self.watch_repository.mark_video_enqueued(
                subscription_id=subscription.id,
                video_id=video.video_id,
                queued_job_id=job.id,
            )
            LOGGER.info(
                "scheduler_video_enqueued subscription_id=%s video_id=%s job_id=%s",
                subscription.id,
                video.video_id,
                job.id,
            )
            enqueued += 1

        return SchedulerPollResult(
            subscriptions_polled=current.subscriptions_polled + 1,
            videos_seen=seen,
            jobs_enqueued=enqueued,
        )
