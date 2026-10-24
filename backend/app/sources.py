"""Source configuration: load and validate `config/sources.yaml`, sync it into the database."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, HttpUrl, field_validator
from sqlalchemy.orm import Session

from app.models import Source


class SourceConfig(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    name: str
    homepage: HttpUrl
    language: Literal["bn", "en"]
    connector: Literal["rss"]  # extend as connectors are added
    feed_url: HttpUrl
    poll_minutes: int = Field(default=30, ge=5, le=1440)
    active: bool = True
    full_text_in_feed: bool = False
    # Derive the section from the first URL path segment (e.g. /sport/abc123 -> "sport").
    section_from_url: bool = False
    notes: str | None = None
    terms_notes: str | None = None

    @field_validator("notes", "terms_notes")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return v.strip() if v else v


class SourcesFile(BaseModel):
    sources: list[SourceConfig]

    @field_validator("sources")
    @classmethod
    def _unique_ids(cls, v: list[SourceConfig]) -> list[SourceConfig]:
        ids = [s.id for s in v]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate source ids: {sorted(dupes)}")
        return v


def load_sources(path: Path) -> list[SourceConfig]:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return SourcesFile.model_validate(data).sources


def sync_sources(session: Session, configs: list[SourceConfig]) -> dict[str, int]:
    """Upsert configured sources. Sources no longer in the file are deactivated, never deleted."""
    existing = {s.id: s for s in session.query(Source).all()}
    created = updated = deactivated = 0
    for cfg in configs:
        values = dict(
            name=cfg.name,
            homepage=str(cfg.homepage),
            language=cfg.language,
            connector=cfg.connector,
            endpoint=str(cfg.feed_url),
            poll_minutes=cfg.poll_minutes,
            active=cfg.active,
            full_text_in_feed=cfg.full_text_in_feed,
            notes=cfg.notes,
            terms_notes=cfg.terms_notes,
            config={"section_from_url": cfg.section_from_url},
        )
        src = existing.get(cfg.id)
        if src is None:
            session.add(Source(id=cfg.id, **values))
            created += 1
        else:
            changed = False
            for key, value in values.items():
                if getattr(src, key) != value:
                    setattr(src, key, value)
                    changed = True
            updated += int(changed)
    configured = {c.id for c in configs}
    for sid, src in existing.items():
        if sid not in configured and src.active:
            src.active = False
            deactivated += 1
    session.commit()
    return {"created": created, "updated": updated, "deactivated": deactivated}
