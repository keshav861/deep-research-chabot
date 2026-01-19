from fastapi import WebSocket
from typing import Any, List, Dict

from multi_agents.agents import ChiefEditorAgent
from backend.utils import write_md_to_word, write_md_to_pdf, write_text_to_md
import sys
import os


class MultiAgentReport:
    def __init__(
        self,
        query: str,
        query_domains: list,
        report_type: str,
        report_source: str,
        source_urls,
        document_urls,
        tone: Any,
        config_path: str,
        websocket: WebSocket,
        headers=None,
        mcp_configs=None,
        mcp_strategy=None,
    ):
        self.query = query
        self.query_domains = query_domains
        self.report_type = report_type
        self.report_source = report_source
        self.source_urls = source_urls
        self.document_urls = document_urls
        self.tone = tone
        self.config_path = config_path
        self.websocket = websocket
        self.headers = headers or {}
        self.visited_urls = set()
        
        # Configure multi-agent parameters
        self.agent_config = {
            "query": self.query,
            "max_sections": 5,  # Default number of sections
            "follow_guidelines": False,
            "model": "gpt-5-chat",  # Using GPT-5-Chat as default model
            "guidelines": [],
            "verbose": True
        }
        
        # Initialize the chief editor agent
        self.chief_editor = ChiefEditorAgent(
            self.agent_config, 
            websocket=self.websocket, 
            stream_output=self._stream_output_handler,
            headers=self.headers
        )
        
        # Initialize the research graph
        self.graph = self.chief_editor.init_research_team().compile()

    async def _stream_output_handler(self, type_str, step, content, websocket=None):
        """Custom handler to stream output from multi-agent system to frontend"""
        if websocket:
            # Format the message to match the expected format in the frontend
            # Send detailed agent progress to research_progress section
            agent_info = ""
            if type_str == "agent":
                agent_info = f"[{step.upper()}] "
            
            await websocket.send_json({
                "type": "logs",
                "output": f"{agent_info}{content}"
            })
        
    async def run(self) -> str:
        """Run the multi-agent research process and return the final report"""
        # Send initial status to frontend
        if self.websocket:
            await self.websocket.send_json({
                "type": "logs",
                "output": "🤖 Initializing multi-agent research team..."
            })
        
        try:
            # Execute the multi-agent workflow
            result = await self.graph.ainvoke({
                "task": self.agent_config
            })
            
            # Extract the final report from the result - check multiple possible keys
            final_report = result.get("report", "")
            if not final_report:
                # Try alternative keys that might contain the final report
                final_report = result.get("final_report", "")
            if not final_report:
                # If still no report, try to construct it from the research state
                if "research_data" in result:
                    sections = []
                    for section in result.get("research_data", []):
                        if isinstance(section, dict):
                            for key, value in section.items():
                                sections.append(str(value))
                        else:
                            sections.append(str(section))
                    
                    # Build a basic report structure
                    title = result.get("title", "Research Report")
                    introduction = result.get("introduction", "")
                    conclusion = result.get("conclusion", "")
                    table_of_contents = result.get("table_of_contents", "")
                    sources = result.get("sources", [])
                    
                    final_report = f"""# {title}

## Table of Contents
{table_of_contents}

## Introduction
{introduction}

## Research Findings
{chr(10).join(sections)}

## Conclusion
{conclusion}

## References
{chr(10).join(f"- {source}" for source in sources)}
"""
            
            # Update visited URLs from research
            if "visited_urls" in result:
                self.visited_urls.update(result["visited_urls"])
            
            # Send the final report to the frontend
            if self.websocket:
                await self.websocket.send_json({
                    "type": "logs",
                    "output": "✅ Multi-agent research completed successfully!"
                })
                
                # Send the final report to be displayed in the research report section
                await self.websocket.send_json({
                    "type": "report",
                    "output": final_report
                })
            
            # Return the final report
            return final_report
            
        except Exception as e:
            error_message = f"❌ Error in multi-agent research: {str(e)}"
            if self.websocket:
                await self.websocket.send_json({
                    "type": "logs",
                    "output": error_message
                })
            raise e
        
    def get_source_urls(self):
        """Return the list of visited URLs during research"""
        return list(self.visited_urls)
        
    def get_costs(self):
        """Return the cost of the research (placeholder)"""
        # In a real implementation, we would track costs across agents
        return 0.0