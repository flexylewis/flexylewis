"""Scraping logic for static and dynamic web pages."""
from __future__ import annotations

import importlib.util
import logging
import time
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional

import requests
from bs4 import BeautifulSoup
from lxml import html

from app.models import ScrapeResult, SelectorConfig

logger = logging.getLogger(__name__)


@dataclass
class ScrapeProgress:
    """Progress update for scraping operations."""

    message: str
    current: int
    total: int


class ScraperError(Exception):
    """Base error raised for scraping failures."""


class Scraper:
    """High-level scraper capable of static or dynamic scraping."""

    def __init__(self, timeout: int = 20) -> None:
        self.timeout = timeout

    def scrape_urls(
        self,
        urls: Iterable[str],
        selectors: SelectorConfig,
        mode: str,
        progress: Optional[Callable[[ScrapeProgress], None]] = None,
    ) -> List[ScrapeResult]:
        """Scrape all provided URLs and return results."""

        results: List[ScrapeResult] = []
        url_list = [url.strip() for url in urls if url.strip()]
        total = len(url_list)

        for index, url in enumerate(url_list, start=1):
            message = f"Scraping {index}/{total}: {url}"
            if progress:
                progress(ScrapeProgress(message=message, current=index, total=total))
            try:
                if mode == "Dynamic (Selenium/Playwright)":
                    html_content = self._fetch_dynamic(url, selectors)
                else:
                    html_content = self._fetch_static(url)

                result = self._extract_fields(url, html_content, selectors)
                results.append(result)
            except Exception as exc:  # noqa: BLE001 - provide user feedback
                logger.exception("Failed to scrape %s", url)
                results.append(ScrapeResult(url=url, content=f"Error: {exc}"))

        if progress:
            progress(ScrapeProgress(message="Done", current=total, total=total))

        return results

    def _fetch_static(self, url: str) -> str:
        """Fetch HTML for a static page using requests."""

        response = requests.get(url, timeout=self.timeout, headers={"User-Agent": "ScraperApp/1.0"})
        response.raise_for_status()
        return response.text

    def _fetch_dynamic(self, url: str, selectors: SelectorConfig) -> str:
        """Fetch HTML for a dynamic page using Playwright or Selenium."""

        if importlib.util.find_spec("playwright") is not None:
            return self._fetch_dynamic_playwright(url, selectors)
        if importlib.util.find_spec("selenium") is not None:
            return self._fetch_dynamic_selenium(url)
        raise ScraperError("Dynamic scraping requires playwright or selenium to be installed.")

    def _fetch_dynamic_playwright(self, url: str, selectors: SelectorConfig) -> str:
        """Fetch HTML with Playwright in headless mode."""

        from playwright.sync_api import sync_playwright

        wait_selector = selectors.content if selectors.content else "body"
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=self.timeout * 1000)
            if wait_selector:
                page.wait_for_selector(wait_selector, timeout=self.timeout * 1000)
            content = page.content()
            browser.close()
        return content

    def _fetch_dynamic_selenium(self, url: str) -> str:
        """Fetch HTML with Selenium in headless mode."""

        from selenium.webdriver import Chrome, ChromeOptions

        options = ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        driver = Chrome(options=options)
        try:
            driver.set_page_load_timeout(self.timeout)
            driver.get(url)
            time.sleep(2)
            return driver.page_source
        finally:
            driver.quit()

    def _extract_fields(self, url: str, html_content: str, selectors: SelectorConfig) -> ScrapeResult:
        """Extract all configured fields from the HTML content."""

        soup = BeautifulSoup(html_content, "html.parser")
        tree = html.fromstring(html_content)

        title = self._extract_single(soup, tree, selectors.title)
        content = self._extract_single(soup, tree, selectors.content)
        price = self._extract_single(soup, tree, selectors.price)
        links = self._extract_links(soup, tree, selectors.links)

        return ScrapeResult(url=url, title=title, content=content, price=price, links=links)

    def _extract_single(self, soup: BeautifulSoup, tree: html.HtmlElement, selector: str) -> str:
        """Extract a single text field via CSS or XPath."""

        if not selector:
            return ""
        if selector.strip().startswith("/") or selector.strip().lower().startswith("xpath="):
            return self._extract_xpath_text(tree, selector)
        elements = soup.select(selector)
        if not elements:
            return ""
        return elements[0].get_text(" ", strip=True)

    def _extract_links(self, soup: BeautifulSoup, tree: html.HtmlElement, selector: str) -> List[str]:
        """Extract a list of links from matching elements."""

        if not selector:
            return []
        if selector.strip().startswith("/") or selector.strip().lower().startswith("xpath="):
            values = self._extract_xpath_all(tree, selector)
            return [value for value in values if value]
        elements = soup.select(selector)
        links = []
        for element in elements:
            href = element.get("href")
            if href:
                links.append(href)
        return links

    def _extract_xpath_text(self, tree: html.HtmlElement, selector: str) -> str:
        """Extract a single text result from XPath."""

        values = self._extract_xpath_all(tree, selector)
        return values[0] if values else ""

    def _extract_xpath_all(self, tree: html.HtmlElement, selector: str) -> List[str]:
        """Extract all XPath results as strings."""

        expression = selector
        if selector.strip().lower().startswith("xpath="):
            expression = selector.split("=", 1)[1].strip()
        results = tree.xpath(expression)
        output: List[str] = []
        for result in results:
            if isinstance(result, str):
                output.append(result.strip())
            else:
                output.append(result.text_content().strip())
        return [value for value in output if value]
