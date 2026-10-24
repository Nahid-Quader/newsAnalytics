import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect

from app.core.config import REPO_ROOT
from app.models import Source
from app.sources import SourcesFile, load_sources, sync_sources

BACKEND = REPO_ROOT / "backend"


def test_repo_sources_file_is_valid():
    sources = load_sources(REPO_ROOT / "config" / "sources.yaml")
    assert {s.id for s in sources} == {"prothomalo-bn", "prothomalo-en", "bdnews24-bn", "bdnews24-en"}


def test_invalid_source_config_rejected():
    base = {"id": "x-1", "name": "X", "homepage": "https://x.org", "language": "bn",
            "connector": "rss", "feed_url": "https://x.org/feed"}
    with pytest.raises(ValidationError):
        SourcesFile.model_validate({"sources": [{**base, "feed_url": "not a url"}]})
    with pytest.raises(ValidationError):
        SourcesFile.model_validate({"sources": [{**base, "language": "fr"}]})
    with pytest.raises(ValidationError, match="duplicate"):
        SourcesFile.model_validate({"sources": [base, base]})


def test_sync_deactivates_removed_sources(session_factory):
    configs = [c for c in load_sources(REPO_ROOT / "config" / "sources.yaml") if c.id != "prothomalo-en"]
    with session_factory() as s:
        result = sync_sources(s, configs)
        assert result["deactivated"] == 1
        assert s.get(Source, "prothomalo-en").active is False


def test_alembic_migration_creates_schema(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.attributes["database_url"] = url
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    tables = set(inspect(create_engine(url)).get_table_names())
    assert {"sources", "articles", "fetch_runs", "alembic_version"} <= tables
    command.downgrade(cfg, "base")
    assert set(inspect(create_engine(url)).get_table_names()) == {"alembic_version"}
