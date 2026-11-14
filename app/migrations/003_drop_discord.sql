ALTER TABLE watched_channels
    DROP CONSTRAINT watched_channels_guild_id_youtube_channel_id_key;

ALTER TABLE watched_channels
    DROP COLUMN guild_id,
    DROP COLUMN discord_channel_id;

ALTER TABLE watched_channels
    ADD CONSTRAINT watched_channels_youtube_channel_id_key UNIQUE (youtube_channel_id);

DROP TABLE IF EXISTS discord_threads;
