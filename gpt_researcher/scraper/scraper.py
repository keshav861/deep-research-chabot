import asyncio
from colorama import Fore, init
import requests
import subprocess
import sys
import importlib
import logging

from gpt_researcher.utils.workers import WorkerPool

from . import (
    ArxivScraper,
    BeautifulSoupScraper,
    PyMuPDFScraper,
)


class Scraper:
    """
    Scraper class to extract the content from the links with detailed logging
    """

    def __init__(self, urls, user_agent, scraper, worker_pool: WorkerPool, websocket=None):
        """
        Initialize the Scraper class.
        Args:
            urls: List of URLs to scrape
            user_agent: User agent string
            scraper: Scraper type
            worker_pool: Worker pool for async operations
            websocket: WebSocket for logging (optional)
        """
        self.urls = urls
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self.scraper = scraper
        self.logger = logging.getLogger(__name__)
        self.worker_pool = worker_pool
        self.websocket = websocket

    async def run(self):
        """
        Extracts the content from the links and logs detailed information
        """
        contents = await asyncio.gather(
            *(self.extract_data_from_url(url, self.session) for url in self.urls)
        )

        res = [content for content in contents if content["raw_content"] is not None]
        
        # Send scraped data summary to websocket for logging
        if self.websocket:
            try:
                scraped_sites = []
                for content in contents:
                    url = content.get("url")
                    raw_content = content.get("raw_content")
                    title = content.get("title", "")
                    
                    # Determine if the site was used
                    used = raw_content is not None and len(raw_content) >= 100
                    skip_reason = ""
                    
                    if not used:
                        if raw_content is None:
                            skip_reason = "Scraping failed or content unavailable"
                        elif len(raw_content) < 100:
                            skip_reason = f"Content too short ({len(raw_content)} characters)"
                    
                    scraped_sites.append({
                        "url": url,
                        "used": used,
                        "skip_reason": skip_reason,
                        "title": title,
                        "content_length": len(raw_content) if raw_content else 0
                    })
                
                await self.websocket.send_json({
                    "type": "scraped_data",
                    "scraped_sites": scraped_sites
                })
            except Exception as e:
                self.logger.error(f"Error sending scraped data to websocket: {e}")
        
        return res

    async def extract_data_from_url(self, link, session):
        """
        Extracts the data from the link with detailed logging
        """
        async with self.worker_pool.throttle():
            try:
                # Log scraping attempt
                if self.websocket:
                    try:
                        await self.websocket.send_json({
                            "type": "logs",
                            "content": "scraping",
                            "output": f"🔍 Scraping: {link}"
                        })
                    except Exception as e:
                        self.logger.warning(f"Error sending websocket message: {e}")
                
                Scraper = self.get_scraper(link)
                scraper = Scraper(link, session)

                # Get scraper name
                scraper_name = scraper.__class__.__name__
                self.logger.info(f"\n=== Using {scraper_name} for {link} ===")

                # Get content
                if hasattr(scraper, "scrape_async"):
                    content, title = await scraper.scrape_async()
                else:
                    content, title = await asyncio.get_running_loop().run_in_executor(
                        self.worker_pool.executor, scraper.scrape
                    )

                # Check content length and log result
                if not content or len(content) < 100:
                    reason = "Content too short or empty"
                    if not content:
                        reason = "No content retrieved"
                    elif len(content) < 100:
                        reason = f"Content too short ({len(content)} characters)"
                    
                    self.logger.warning(f"{reason} for {link}")
                    
                    # Log to websocket
                    if self.websocket:
                        try:
                            await self.websocket.send_json({
                                "type": "source_update",
                                "url": link,
                                "used": False,
                                "skip_reason": reason,
                                "title": title,
                                "content_length": len(content) if content else 0
                            })
                        except Exception as e:
                            self.logger.warning(f"Error sending websocket update: {e}")
                    
                    return {
                        "url": link,
                        "raw_content": None,
                        "title": title,
                    }

                # Log successful scraping
                self.logger.info(f"\nTitle: {title}")
                self.logger.info(
                    f"Content length: {len(content) if content else 0} characters"
                )
                self.logger.info(f"URL: {link}")
                self.logger.info("=" * 50)

                # Log success to websocket
                if self.websocket:
                    try:
                        await self.websocket.send_json({
                            "type": "source_update",
                            "url": link,
                            "used": True,
                            "skip_reason": "",
                            "title": title,
                            "content_length": len(content)
                        })
                        
                        await self.websocket.send_json({
                            "type": "logs",
                            "content": "scraping_success",
                            "output": f"✅ Successfully scraped: {link} ({len(content)} chars)"
                        })
                    except Exception as e:
                        self.logger.warning(f"Error sending websocket update: {e}")

                return {
                    "url": link,
                    "raw_content": content,
                    "title": title,
                }

            except Exception as e:
                error_msg = f"Error processing {link}: {str(e)}"
                self.logger.error(error_msg)
                
                # Log error to websocket
                if self.websocket:
                    try:
                        await self.websocket.send_json({
                            "type": "source_update",
                            "url": link,
                            "used": False,
                            "skip_reason": f"Scraping error: {str(e)}",
                            "title": "",
                            "content_length": 0
                        })
                        
                        await self.websocket.send_json({
                            "type": "logs",
                            "content": "scraping_error",
                            "output": f"❌ Failed to scrape: {link} - {str(e)}"
                        })
                    except Exception as ws_error:
                        self.logger.warning(f"Error sending websocket update: {ws_error}")
                
                return {"url": link, "raw_content": None, "title": ""}

    def get_scraper(self, link):
        """
        The function `get_scraper` determines the appropriate scraper class based on the provided link
        or a default scraper if none matches.

        Args:
          link: The `get_scraper` method takes a `link` parameter which is a URL link to a webpage or a
        PDF file. Based on the type of content the link points to, the method determines the appropriate
        scraper class to use for extracting data from that content.

        Returns:
          The `get_scraper` method returns the scraper class based on the provided link. The method
        checks the link to determine the appropriate scraper class to use based on predefined mappings
        in the `SCRAPER_CLASSES` dictionary. If the link ends with ".pdf", it selects the
        `PyMuPDFScraper` class. If the link contains "arxiv.org", it selects the `ArxivScraper
        """

        SCRAPER_CLASSES = {
            "pdf": PyMuPDFScraper,
            "arxiv": ArxivScraper,
            "bs": BeautifulSoupScraper,
        }

        scraper_key = None

        if link.endswith(".pdf"):
            scraper_key = "pdf"
        elif "arxiv.org" in link:
            scraper_key = "arxiv"
        else:
            scraper_key = self.scraper

        scraper_class = SCRAPER_CLASSES.get(scraper_key)
        if scraper_class is None:
            raise Exception("Scraper not found.")

        return scraper_class