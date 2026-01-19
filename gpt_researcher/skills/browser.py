from gpt_researcher.utils.workers import WorkerPool

from ..actions.utils import stream_output
from ..actions.web_scraping import scrape_urls


class BrowserManager:
    """Manages context for the researcher agent."""

    def __init__(self, researcher):
        self.researcher = researcher
        self.worker_pool = WorkerPool(researcher.cfg.max_scraper_workers)

    async def browse_urls(self, urls: list[str]) -> list[dict]:
        """
        Scrape content from a list of URLs with detailed logging.

        Args:
            urls (list[str]): list of URLs to scrape.

        Returns:
            list[dict]: list of scraped content results.
        """
        if self.researcher.verbose:
            await stream_output(
                "logs",
                "scraping_urls",
                f"🌐 Scraping content from {len(urls)} URLs...",
                self.researcher.websocket,
            )

        # ===== UPDATED: Pass websocket for detailed source logging =====
        scraped_content, _ = await scrape_urls(
            urls, 
            self.researcher.cfg, 
            self.worker_pool,
            websocket=self.researcher.websocket  # <- ADD THIS LINE
        )
        # ================================================================
        
        self.researcher.add_research_sources(scraped_content)

        if self.researcher.verbose:
            await stream_output(
                "logs",
                "scraping_content",
                f"📄 Scraped {len(scraped_content)} pages of content",
                self.researcher.websocket,
            )
            await stream_output(
                "logs",
                "scraping_complete",
                "🌐 Scraping complete",
                self.researcher.websocket,
            )

        return scraped_content