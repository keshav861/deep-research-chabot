import asyncio
from typing import List, Dict, Set, Optional, Any
from fastapi import WebSocket

from gpt_researcher import GPTResearcher


class DetailedReport:
    def __init__(
        self,
        query: str,
        report_type: str,
        report_source: str,
        source_urls: List[str] = [],
        document_urls: List[str] = [],
        query_domains: List[str] = [],
        config_path: str = None,
        tone: Any = "",
        websocket: WebSocket = None,
        subtopics: List[Dict] = [],
        headers: Optional[Dict] = None,
        complement_source_urls: bool = False,
        mcp_configs=None,
        mcp_strategy=None,
    ):
        self.query = query
        self.report_type = report_type
        self.report_source = report_source
        self.source_urls = source_urls
        self.document_urls = document_urls
        self.query_domains = query_domains
        self.config_path = config_path
        self.tone = tone
        self.websocket = websocket
        self.subtopics = subtopics
        self.headers = headers or {}
        self.complement_source_urls = complement_source_urls
        
        # Initialize researcher with optional MCP parameters
        gpt_researcher_params = {
            "query": self.query,
            "query_domains": self.query_domains,
            "report_type": "research_report",
            "report_source": self.report_source,
            "source_urls": self.source_urls,
            "document_urls": self.document_urls,
            "config_path": self.config_path,
            "tone": self.tone,
            "websocket": self.websocket,
            "headers": self.headers,
            "complement_source_urls": self.complement_source_urls,
        }
        
        # Add MCP parameters if provided
        if mcp_configs is not None:
            gpt_researcher_params["mcp_configs"] = mcp_configs
        if mcp_strategy is not None:
            gpt_researcher_params["mcp_strategy"] = mcp_strategy
            
        self.gpt_researcher = GPTResearcher(**gpt_researcher_params)
        self.existing_headers: List[Dict] = []
        self.global_context: List[str] = []
        self.global_written_sections: List[str] = []
        self.global_urls: Set[str] = set(
            self.source_urls) if self.source_urls else set()

    async def run(self) -> str:
        """
        Run the detailed report generation process.
        Only the final complete report is sent to the frontend.
        """
        # Conduct initial research (this can still show progress)
        await self._initial_research()
        
        # Get all subtopics
        subtopics = await self._get_all_subtopics()
        
        # CRITICAL: Store the original websocket and disable it for all intermediate operations
        original_ws = self.gpt_researcher.websocket
        original_verbose = self.gpt_researcher.verbose
        
        # Disable websocket and verbose mode for ALL intermediate report generation
        self.gpt_researcher.websocket = None
        self.gpt_researcher.verbose = False
        
        # Generate introduction (silently - no streaming)
        report_introduction = await self.gpt_researcher.write_introduction()
        
        # Generate all subtopic reports (silently - no streaming)
        _, report_body = await self._generate_subtopic_reports(subtopics)
        
        # Update visited URLs
        self.gpt_researcher.visited_urls.update(self.global_urls)
        
        # Construct the final detailed report (silently - no streaming)
        report = await self._construct_detailed_report(report_introduction, report_body)
        
        # Restore websocket and verbose settings
        self.gpt_researcher.websocket = original_ws
        self.gpt_researcher.verbose = original_verbose
        
        # NOW send ONLY the final complete report to frontend (matching MultiAgentReport pattern)
        if self.websocket:
            await self.websocket.send_json({
                "type": "logs",
                "output": "✅ Detailed research report generated successfully!"
            })
            await self.websocket.send_json({
                "type": "report",
                "output": report
            })
        
        return report

    async def _initial_research(self) -> None:
        """Conduct initial research - this can show progress"""
        await self.gpt_researcher.conduct_research()
        self.global_context = self.gpt_researcher.context
        self.global_urls = self.gpt_researcher.visited_urls

    async def _get_all_subtopics(self) -> List[Dict]:
        """Get all subtopics for the research"""
        subtopics_data = await self.gpt_researcher.get_subtopics()

        all_subtopics = []
        if subtopics_data and subtopics_data.subtopics:
            for subtopic in subtopics_data.subtopics:
                all_subtopics.append({"task": subtopic.task})
        else:
            print(f"Unexpected subtopics data format: {subtopics_data}")

        return all_subtopics

    async def _generate_subtopic_reports(self, subtopics: List[Dict]) -> tuple:
        """Generate reports for all subtopics silently"""
        subtopic_reports = []
        subtopics_report_body = ""

        for subtopic in subtopics:
            result = await self._get_subtopic_report(subtopic)
            if result["report"]:
                subtopic_reports.append(result)
                subtopics_report_body += f"\n\n\n{result['report']}"

        return subtopic_reports, subtopics_report_body

    async def _get_subtopic_report(self, subtopic: Dict) -> Dict[str, str]:
        """
        Generate a single subtopic report.
        CRITICAL: This runs completely silently - no streaming to frontend.
        """
        current_subtopic_task = subtopic.get("task")
        
        # CRITICAL FIX: Create subtopic assistant with NO websocket and verbose=False
        # This prevents ANY intermediate streaming to the frontend
        subtopic_assistant = GPTResearcher(
            query=current_subtopic_task,
            query_domains=self.query_domains,
            report_type="subtopic_report",
            report_source=self.report_source,
            websocket=None,  # NO websocket for subtopics
            verbose=False,   # NO verbose logging for subtopics
            headers=self.headers,
            parent_query=self.query,
            subtopics=self.subtopics,
            visited_urls=self.global_urls,
            agent=self.gpt_researcher.agent,
            role=self.gpt_researcher.role,
            tone=self.tone,
            complement_source_urls=self.complement_source_urls,
            source_urls=self.source_urls
        )

        subtopic_assistant.context = list(set(self.global_context))
        
        # Conduct research silently
        await subtopic_assistant.conduct_research()

        # Get draft section titles
        draft_section_titles = await subtopic_assistant.get_draft_section_titles(current_subtopic_task)

        if not isinstance(draft_section_titles, str):
            draft_section_titles = str(draft_section_titles)

        parse_draft_section_titles = self.gpt_researcher.extract_headers(draft_section_titles)
        parse_draft_section_titles_text = [header.get(
            "text", "") for header in parse_draft_section_titles]

        relevant_contents = await subtopic_assistant.get_similar_written_contents_by_draft_section_titles(
            current_subtopic_task, parse_draft_section_titles_text, self.global_written_sections
        )

        # Generate subtopic report silently (no streaming)
        subtopic_report = await subtopic_assistant.write_report(self.existing_headers, relevant_contents)

        # Update global state with subtopic results
        self.global_written_sections.extend(self.gpt_researcher.extract_sections(subtopic_report))
        self.global_context = list(set(subtopic_assistant.context))
        self.global_urls.update(subtopic_assistant.visited_urls)

        self.existing_headers.append({
            "subtopic task": current_subtopic_task,
            "headers": self.gpt_researcher.extract_headers(subtopic_report),
        })

        return {"topic": subtopic, "report": subtopic_report}

    async def _construct_detailed_report(self, introduction: str, report_body: str) -> str:
        """Construct the final detailed report from all components"""
        toc = self.gpt_researcher.table_of_contents(report_body)
        conclusion = await self.gpt_researcher.write_report_conclusion(report_body)
        conclusion_with_references = self.gpt_researcher.add_references(
            conclusion, self.gpt_researcher.visited_urls)
        report = f"{introduction}\n\n{toc}\n\n{report_body}\n\n{conclusion_with_references}"
        return report