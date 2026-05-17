from app.youtube_urls import InvalidYouTubeUrl, parse_youtube_url


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
