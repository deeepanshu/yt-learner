from app.youtube_urls import InvalidYouTubeUrl, parse_youtube_url, parse_youtube_url_or_id


def test_parse_standard_watch_url() -> None:
    parsed = parse_youtube_url("https://www.youtube.com/watch?v=abc123xyz")
    assert parsed.video_id == "abc123xyz"
    assert parsed.canonical_url == "https://www.youtube.com/watch?v=abc123xyz"


def test_parse_short_url() -> None:
    parsed = parse_youtube_url("https://youtu.be/abc123xyz?t=10")
    assert parsed.video_id == "abc123xyz"


def test_parse_invalid_url() -> None:
    try:
        parse_youtube_url("https://example.com/watch?v=abc123xyz")
    except InvalidYouTubeUrl:
        return
    raise AssertionError("Expected InvalidYouTubeUrl")


def test_parse_youtube_url_or_id_accepts_video_id() -> None:
    parsed = parse_youtube_url_or_id("dQw4w9WgXcQ")
    assert parsed.video_id == "dQw4w9WgXcQ"
    assert parsed.canonical_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_parse_youtube_url_or_id_accepts_watch_url() -> None:
    parsed = parse_youtube_url_or_id("https://www.youtube.com/watch?v=abc123xyz")
    assert parsed.video_id == "abc123xyz"


def test_parse_youtube_url_or_id_rejects_invalid_input() -> None:
    try:
        parse_youtube_url_or_id("not a youtube video")
    except InvalidYouTubeUrl:
        return
    raise AssertionError("Expected InvalidYouTubeUrl")
