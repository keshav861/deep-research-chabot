from typing import Dict, Optional, List
import json
from ..config.config import Config
from ..utils.llm import create_chat_completion
from ..actions import stream_output


class SourceCurator:
    """Ranks sources and curates data based on their relevance, credibility and reliability."""

    def __init__(self, researcher):
        self.researcher = researcher

    async def curate_sources(
        self,
        source_data: List,
        max_results: int = 50,
    ) -> tuple[List, Dict]:
        """
        Rank sources based on research data and guidelines.

        Args:
            query: The research query/task
            source_data: List of source documents to rank
            max_results: Maximum number of top sources to return

        Returns:
            tuple: (curated_sources list, curator_decisions dict)
        """
        print(f"\n\nCurating {len(source_data)} sources: {source_data}")
        if self.researcher.verbose:
            await stream_output(
                "logs",
                "research_plan",
                f"⚖️ Evaluating and curating sources by credibility and relevance...",
                self.researcher.websocket,
            )

        response = ""
        curator_decisions = {}  # Track curator decisions for each URL
        
        try:
            # Create a mapping of URLs from source_data for tracking
            url_to_source = {item.get('url'): item for item in source_data if isinstance(item, dict) and item.get('url')}
            
            response = await create_chat_completion(
                model=self.researcher.cfg.smart_llm_model,
                messages=[
                    {"role": "system", "content": f"{self.researcher.role}"},
                    {"role": "user", "content": self.researcher.prompt_family.curate_sources(
                        self.researcher.query, source_data, max_results)},
                ],
                temperature=0.2,
                max_tokens=8000,
                llm_provider=self.researcher.cfg.smart_llm_provider,
                llm_kwargs=self.researcher.cfg.llm_kwargs,
                cost_callback=self.researcher.add_costs,
            )

            curated_sources = json.loads(response)
            print(f"\n\nFinal Curated sources {len(curated_sources)} sources: {curated_sources}")

            # Create set of kept URLs for easy lookup
            kept_urls = set()
            for source in curated_sources:
                if isinstance(source, dict) and source.get('url'):
                    kept_urls.add(source['url'])
            
            # Track decisions for all sources
            for url, original_source in url_to_source.items():
                if url in kept_urls:
                    curator_decisions[url] = {
                        'kept': True,
                        'reason': 'Selected by LLM curator as relevant and credible'
                    }
                else:
                    curator_decisions[url] = {
                        'kept': False,
                        'reason': 'Rejected by LLM curator - insufficient relevance, credibility, or quality'
                    }

            if self.researcher.verbose:
                await stream_output(
                    "logs",
                    "research_plan",
                    f"🏆 Verified and ranked top {len(curated_sources)} most reliable sources",
                    self.researcher.websocket,
                )

            return curated_sources, curator_decisions

        except Exception as e:
            print(f"Error in curate_sources from LLM response: {response}")
            if self.researcher.verbose:
                await stream_output(
                    "logs",
                    "research_plan",
                    f"🚫 Source verification failed: {str(e)}",
                    self.researcher.websocket,
                )
            
            # If curation fails, mark all as kept (no curation applied)
            for item in source_data:
                if isinstance(item, dict) and item.get('url'):
                    curator_decisions[item['url']] = {
                        'kept': True,
                        'reason': 'Curation failed - source included by default'
                    }
            
            return source_data, curator_decisions