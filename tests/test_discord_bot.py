from app.discord_bot import extract_youtube_url


def test_extract_youtube_url_from_plain_message() -> None:
    content = "check this out https://www.youtube.com/watch?v=abc123xyz thanks"
    assert extract_youtube_url(content) == "https://www.youtube.com/watch?v=abc123xyz"


def test_extract_youtube_url_from_parenthesized_message() -> None:
    content = "(https://youtu.be/abc123xyz)"
    assert extract_youtube_url(content) == "https://youtu.be/abc123xyz"


def test_extract_youtube_url_returns_none_when_missing() -> None:
    assert extract_youtube_url("hello world") is None
