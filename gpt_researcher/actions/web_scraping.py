from typing import Any
from colorama import Fore, Style

from gpt_researcher.utils.workers import WorkerPool
from ..scraper import Scraper
from ..config.config import Config
from ..utils.logger import get_formatted_logger

logger = get_formatted_logger()


async def scrape_urls(
    urls, cfg: Config, worker_pool: WorkerPool, websocket=None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Scrapes the urls with detailed logging support
    Args:
        urls: List of urls
        cfg: Config
        worker_pool: Worker pool for async operations
        websocket: WebSocket for logging (optional)

    Returns:
        tuple[list[dict[str, Any]], list[dict[str, Any]]]: tuple containing scraped content and placeholder for backwards compatibility
    """
    scraped_data = []
    user_agent = (
        cfg.user_agent
        if cfg
        else "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )

    try:
        # Pass websocket to scraper for detailed logging
        scraper = Scraper(urls, user_agent, cfg.scraper, worker_pool=worker_pool, websocket=websocket)
        scraped_data = await scraper.run()
        
        # Log summary
        if websocket:
            try:
                total_urls = len(urls)
                successful_scrapes = len(scraped_data)
                failed_scrapes = total_urls - successful_scrapes
                
                await websocket.send_json({
                    "type": "logs",
                    "content": "scraping_complete",
                    "output": f"📊 Scraping complete: {successful_scrapes}/{total_urls} successful, {failed_scrapes} failed"
                })
            except Exception as e:
                logger.warning(f"Error sending scraping summary: {e}")
                
    except Exception as e:
        logger.error(f"{Fore.RED}Error in scrape_urls: {e}{Style.RESET_ALL}")
        
        if websocket:
            try:
                await websocket.send_json({
                    "type": "logs",
                    "content": "error",
                    "output": f"❌ Error in scraping process: {e}"
                })
            except Exception as ws_error:
                logger.warning(f"Error sending error message to websocket: {ws_error}")

    return scraped_data, []  # Return empty list for images as they are no longer supported


async def filter_urls(urls: list[str], config: Config) -> list[str]:
    """
    Filter URLs based on configuration settings.

    Args:
        urls (list[str]): List of URLs to filter.
        config (Config): Configuration object.

    Returns:
        list[str]: Filtered list of URLs.
    """
    filtered_urls = []
    for url in urls:
        # Add your filtering logic here
        # For example, you might want to exclude certain domains or URL patterns
        if not any(excluded in url for excluded in config.excluded_domains):
            filtered_urls.append(url)
    return filtered_urls

async def extract_main_content(html_content: str) -> str:
    """
    Extract the main content from HTML.

    Args:
        html_content (str): Raw HTML content.

    Returns:
        str: Extracted main content.
    """
    # Implement content extraction logic here
    # This could involve using libraries like BeautifulSoup or custom parsing logic
    # For now, we'll just return the raw HTML as a placeholder
    return html_content

async def process_scraped_data(scraped_data: list[dict[str, Any]], config: Config) -> list[dict[str, Any]]:
    """
    Process the scraped data to extract and clean the main content.

    Args:
        scraped_data (list[dict[str, Any]]): List of dictionaries containing scraped data.
        config (Config): Configuration object.

    Returns:
        list[dict[str, Any]]: Processed scraped data.
    """
    processed_data = []
    for item in scraped_data:
        if item.get('raw_content'):  # Changed from 'status' to 'raw_content' check
            main_content = await extract_main_content(item['raw_content'])
            processed_data.append({
                'url': item['url'],
                'content': main_content,
                'title': item.get('title', ''),
                'raw_content': item['raw_content']
            })
        else:
            processed_data.append(item)
    return processed_data