import os

from app.config import _read_env_file, load_environment_files


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


def test_load_environment_files_layers_shared_secrets_and_local_env(tmp_path, monkeypatch) -> None:
    shared_dir = tmp_path / "home" / "deepanshu" / "config"
    shared_dir.mkdir(parents=True)
    (shared_dir / "shared.env").write_text("OPENAI_MODEL=shared\n", encoding="utf-8")
    (shared_dir / "shared.secrets.env").write_text("DISCORD_BOT_TOKEN=shared-secret\n", encoding="utf-8")
    local_env = tmp_path / "repo" / ".env"
    local_env.parent.mkdir()
    local_env.write_text("OPENAI_MODEL=local\nOPENAI_API_KEY=local-key\n", encoding="utf-8")

    monkeypatch.chdir(local_env.parent)
    monkeypatch.setattr(
        "app.config.SHARED_ENV_PATHS",
        (shared_dir / "shared.env", shared_dir / "shared.secrets.env"),
    )
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)

    load_environment_files()

    assert os.environ["OPENAI_MODEL"] == "local"
    assert os.environ["OPENAI_API_KEY"] == "local-key"
    assert os.environ["DISCORD_BOT_TOKEN"] == "shared-secret"
