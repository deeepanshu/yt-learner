import os

from app.config import _read_env_file, load_environment_file


def test_read_env_file_parses_simple_values(tmp_path) -> None:
    env_file = tmp_path / "sample.env"
    env_file.write_text(
        "# comment\n"
        "OPENAI_MODEL=gpt-4o-mini\n"
        "QUOTED=\"quoted value\"\n"
        "EMPTY=\n"
        "invalid-line\n",
        encoding="utf-8",
    )

    values = _read_env_file(env_file)

    assert values == {
        "OPENAI_MODEL": "gpt-4o-mini",
        "QUOTED": "quoted value",
        "EMPTY": "",
    }


def test_load_environment_file_reads_repo_local_env_only(tmp_path, monkeypatch) -> None:
    local_env = tmp_path / "repo" / ".env"
    local_env.parent.mkdir()
    local_env.write_text(
        "OPENAI_MODEL=local\nOPENAI_API_KEY=local-key\nDISCORD_BOT_TOKEN=local-token\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(local_env.parent)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)

    load_environment_file()

    assert os.environ["OPENAI_MODEL"] == "local"
    assert os.environ["OPENAI_API_KEY"] == "local-key"
    assert os.environ["DISCORD_BOT_TOKEN"] == "local-token"
