"""Minimal FastAPI service: topic search with a 5-minute cache.

Searches what is being said about a term via Google News RSS, persists
metadata and result in Postgres, and serves the cached result for 5 minutes.
"""

import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import httpx
from fastapi import Depends, FastAPI, HTTPException
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import JSON, DateTime, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

DEFAULT_TTL_SECONDS = 300
NEWS_RSS_URL = "https://news.google.com/rss/search?q={q}"
REQUEST_TIMEOUT_SECONDS = 12


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str
    ttl_seconds: int = DEFAULT_TTL_SECONDS


settings = Settings()

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    pass


class TopicSearch(Base):
    """A cached search for a term."""

    __tablename__ = "topic_searches"

    id: Mapped[int] = mapped_column(primary_key=True)
    term: Mapped[str] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    result: Mapped[dict] = mapped_column(JSON)


Base.metadata.create_all(engine)

app = FastAPI(title="Topic Search")


def get_db() -> Session:
    """Yield a database session, committing and closing on teardown."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def search_web(term: str) -> dict:
    """Fetch Google News RSS entries for the term.

    Raises:
        HTTPException: If the news feed cannot be fetched or parsed.
    """
    try:
        response = httpx.get(
            NEWS_RSS_URL.format(q=quote(term)),
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": "Mozilla/5.0"},
            follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"No se pudo consultar Google News para '{term}'.") from exc

    try:
        root = ET.fromstring(response.content)
        items = []
        for item in root.findall(".//item"):
            source_el = item.find("source")
            items.append(
                {
                    "title": item.findtext("title"),
                    "link": item.findtext("link"),
                    "published": item.findtext("pubDate"),
                    "source": source_el.text if source_el is not None else None,
                }
            )
        return {"query": term, "count": len(items), "results": items}
    except ET.ParseError as exc:
        raise HTTPException(502, f"No se pudo parsear el feed para '{term}'.") from exc


@app.get("/topics/{term}")
def get_topic(term: str, db: Session = Depends(get_db)) -> dict:
    """Return current chatter for a term, using the cache when fresh."""
    latest = db.scalar(
        select(TopicSearch).where(TopicSearch.term == term).order_by(TopicSearch.created_at.desc()).limit(1)
    )
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.ttl_seconds)
    if latest is not None and latest.created_at > cutoff:
        return latest.result

    result = search_web(term)
    db.add(TopicSearch(term=term, result=result))
    db.commit()
    return result
