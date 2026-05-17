from app.youtube_channels import ResolvedYouTubeChannel, resolve_youtube_channel


def test_resolve_youtube_channel_uses_external_id_fallback(monkeypatch) -> None:
    page_html = """
    <html>
      <head>
        <meta property="og:title" content="Matt Pocock">
      </head>
      <body>
        {"externalId":"UCswG6FSbgZjbWtdf_hMLaow","canonicalBaseUrl":"/@mattpocockuk"}
      </body>
    </html>
    """
    monkeypatch.setattr("app.youtube_channels._fetch_text", lambda url: page_html)

    resolved = resolve_youtube_channel("https://www.youtube.com/@mattpocockuk")

    assert resolved == ResolvedYouTubeChannel(
        channel_id="UCswG6FSbgZjbWtdf_hMLaow",
        title="Matt Pocock",
        canonical_url="https://www.youtube.com/channel/UCswG6FSbgZjbWtdf_hMLaow",
    )


def test_resolve_youtube_channel_uses_og_url_fallback(monkeypatch) -> None:
    page_html = """
    <html>
      <head>
        <meta property="og:title" content="AI Engineer">
        <meta property="og:url" content="https://www.youtube.com/channel/UCLKPca3kwwd-B59HNr-_lvA">
      </head>
      <body></body>
    </html>
    """
    monkeypatch.setattr("app.youtube_channels._fetch_text", lambda url: page_html)

    resolved = resolve_youtube_channel("@aiengineer")

    assert resolved == ResolvedYouTubeChannel(
        channel_id="UCLKPca3kwwd-B59HNr-_lvA",
        title="AI Engineer",
        canonical_url="https://www.youtube.com/channel/UCLKPca3kwwd-B59HNr-_lvA",
    )
