"""Data models for scraped records and configuration."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class SelectorConfig:
    """Selectors used to extract fields from each page."""

    title: str = "title"
    content: str = "body"
    price: str = ".price"
    links: str = "a"


@dataclass
class ScrapeResult:
    """Structured output for a single scraped URL."""

    url: str
    title: str = ""
    content: str = ""
    price: str = ""
    links: List[str] = field(default_factory=list)

    def links_text(self) -> str:
        """Return a human-readable representation of links."""

        return ", ".join(self.links)
