import os

from app.config import load_environment_file


def test_load_environment_file_reads_repo_local_env_only(tmp_path, monkeypatch) -> None:
    local_env = tmp_path / "repo" / ".env"
    local_env.parent.mkdir()
    local_env.write_text(
        "OLLAMA_MODEL=local\nOLLAMA_API_KEY=local-key\nTRILIUM_ETAPI_TOKEN=local-token\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(local_env.parent)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.delenv("TRILIUM_ETAPI_TOKEN", raising=False)

    load_environment_file()

    assert os.environ["OLLAMA_MODEL"] == "local"
    assert os.environ["OLLAMA_API_KEY"] == "local-key"
    assert os.environ["TRILIUM_ETAPI_TOKEN"] == "local-token"
