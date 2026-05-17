from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.channel_watches import WatchRepository
from app.job_queue import JobQueue
from app.scheduler import ChannelScheduler
from app.storage import OutputStore
from app.youtube_channels import ChannelFeedVideo


@dataclass
class FakeFeedFetcher:
    videos_by_channel: dict[str, list[ChannelFeedVideo]]

    def __call__(self, channel_id: str) -> tuple[str, list[ChannelFeedVideo]]:
        return channel_id, list(self.videos_by_channel.get(channel_id, []))


def test_bootstrap_records_existing_feed_without_queueing(tmp_path) -> None:
    repository = WatchRepository(tmp_path / "data" / "yt_learner.sqlite3")
    queue = JobQueue(tmp_path / "data" / "yt_learner.sqlite3")
    store = OutputStore(tmp_path / "outputs", tmp_path / "data" / "yt_learner.sqlite3")
    subscription = repository.add_or_update_subscription(
        guild_id="guild-1",
        youtube_channel_id="UC12345678901234567890",
        youtube_channel_ref="https://www.youtube.com/channel/UC12345678901234567890",
        youtube_channel_title="AI Channel",
        discord_channel_id=1001,
    )
    scheduler = ChannelScheduler(
        watch_repository=repository,
        queue=queue,
        store=store,
        feed_fetcher=FakeFeedFetcher(
            {
                subscription.youtube_channel_id: [
                    build_feed_video("old-1", 1),
                    build_feed_video("old-2", 2),
                ]
            }
        ),
    )

    result = run_async(scheduler.poll_once())

    assert result.subscriptions_polled == 1
    assert result.videos_seen == 2
    assert result.jobs_enqueued == 0
    assert queue.claim_next_job() is None
    videos = repository.list_discovered_videos(subscription_id=subscription.id)
    assert [video.video_id for video in videos] == ["old-1", "old-2"]
    assert repository.get_active_subscriptions()[0].bootstrap_completed_at is not None


def test_new_video_after_bootstrap_is_queued_once(tmp_path) -> None:
    repository = WatchRepository(tmp_path / "data" / "yt_learner.sqlite3")
    queue = JobQueue(tmp_path / "data" / "yt_learner.sqlite3")
    store = OutputStore(tmp_path / "outputs", tmp_path / "data" / "yt_learner.sqlite3")
    subscription = repository.add_or_update_subscription(
        guild_id="guild-1",
        youtube_channel_id="UC12345678901234567890",
        youtube_channel_ref="https://www.youtube.com/channel/UC12345678901234567890",
        youtube_channel_title="AI Channel",
        discord_channel_id=1001,
    )
    fetcher = FakeFeedFetcher(
        {
            subscription.youtube_channel_id: [
                build_feed_video("new-2", 2),
                build_feed_video("new-1", 1),
            ]
        }
    )
    scheduler = ChannelScheduler(
        watch_repository=repository,
        queue=queue,
        store=store,
        feed_fetcher=fetcher,
    )

    run_async(scheduler.poll_once())
    result = run_async(scheduler.poll_once())
    claimed = queue.claim_next_job()

    assert result.videos_seen == 0
    assert result.jobs_enqueued == 0
    assert claimed is None

    fetcher.videos_by_channel[subscription.youtube_channel_id] = [
        build_feed_video("new-3", 3),
        build_feed_video("new-2", 2),
        build_feed_video("new-1", 1),
    ]

    result = run_async(scheduler.poll_once())
    claimed = queue.claim_next_job()

    assert result.videos_seen == 1
    assert result.jobs_enqueued == 1
    assert claimed is not None
    assert claimed.video_url == "https://www.youtube.com/watch?v=new-3"
    discovered = repository.list_discovered_videos(subscription_id=subscription.id)
    assert sorted(video.video_id for video in discovered) == ["new-1", "new-2", "new-3"]
    assert discovered[-1].queued_job_id == claimed.id


def test_existing_learning_record_is_not_requeued(tmp_path) -> None:
    repository = WatchRepository(tmp_path / "data" / "yt_learner.sqlite3")
    queue = JobQueue(tmp_path / "data" / "yt_learner.sqlite3")
    store = OutputStore(tmp_path / "outputs", tmp_path / "data" / "yt_learner.sqlite3")
    subscription = repository.add_or_update_subscription(
        guild_id="guild-1",
        youtube_channel_id="UC12345678901234567890",
        youtube_channel_ref="https://www.youtube.com/channel/UC12345678901234567890",
        youtube_channel_title="AI Channel",
        discord_channel_id=1001,
    )
    store.save_markdown(
        title="Already Learned",
        video_id="known-video",
        source_url="https://www.youtube.com/watch?v=known-video",
        markdown="# Already Learned",
        requested_by="user-1",
    )
    scheduler = ChannelScheduler(
        watch_repository=repository,
        queue=queue,
        store=store,
        feed_fetcher=FakeFeedFetcher(
            {
                subscription.youtube_channel_id: [build_feed_video("known-video", 1)]
            }
        ),
    )

    run_async(scheduler.poll_once())
    result = run_async(scheduler.poll_once())

    assert result.videos_seen == 0
    assert result.jobs_enqueued == 0

    scheduler.feed_fetcher.videos_by_channel[subscription.youtube_channel_id] = [
        build_feed_video("fresh-video", 2),
        build_feed_video("known-video", 1),
    ]
    result = run_async(scheduler.poll_once())
    jobs = [queue.claim_next_job(), queue.claim_next_job()]

    assert result.videos_seen == 1
    assert result.jobs_enqueued == 1
    assert jobs[0] is not None
    assert jobs[0].video_url == "https://www.youtube.com/watch?v=fresh-video"
    assert jobs[1] is None


def build_feed_video(video_id: str, day: int) -> ChannelFeedVideo:
    return ChannelFeedVideo(
        video_id=video_id,
        title=f"Video {video_id}",
        video_url=f"https://www.youtube.com/watch?v={video_id}",
        published_at=datetime(2026, 5, day, tzinfo=timezone.utc),
    )


def run_async(awaitable):
    import asyncio

    return asyncio.run(awaitable)
