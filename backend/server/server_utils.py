import asyncio
import json
import os
import re
import time
import shutil
import traceback
from typing import Awaitable, Dict, List, Any
from fastapi.responses import JSONResponse, FileResponse
from gpt_researcher.document.document import DocumentLoader
from gpt_researcher import GPTResearcher
from backend.utils import write_md_to_pdf, write_md_to_word, write_text_to_md
from pathlib import Path
from datetime import datetime
from fastapi import HTTPException
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class CustomLogsHandler:
    """Custom handler to capture streaming logs from the research process"""
    def __init__(self, websocket, task: str):
        self.logs = []
        self.websocket = websocket
        sanitized_filename = sanitize_filename(f"task_{int(time.time())}_{task}")
        self.log_file = os.path.join("outputs", f"{sanitized_filename}.json")
        self.timestamp = datetime.now().isoformat()
        # Initialize log file with metadata
        os.makedirs("outputs", exist_ok=True)
        with open(self.log_file, 'w') as f:
            json.dump({
                "timestamp": self.timestamp,
                "events": [],
                "content": {
                    "query": task,
                    "sources": [],
                    "context": [],
                    "report": "",
                    "costs": 0.0,
                    "curator_decisions": {}
                }
            }, f, indent=2)

    async def send_json(self, data: Dict[str, Any]) -> None:
        """Store log data and send to websocket"""
        # Send to websocket for real-time display
        if self.websocket:
            await self.websocket.send_json(data)
            
        # Read current log file
        with open(self.log_file, 'r') as f:
            log_data = json.load(f)
            
        # Update appropriate section based on data type
        if data.get('type') == 'logs':
            log_data['events'].append({
                "timestamp": datetime.now().isoformat(),
                "type": "event",
                "data": data
            })
            
            # === NEW: Capture source URL information from logs ===
            content = data.get('content', '')
            output = data.get('output', '')
            
            # Check if this is a scraping event
            if 'scraping' in content.lower() or 'scraping' in output.lower():
                # Extract URL from the output
                url_match = re.search(r'https?://[^\s<>"{}|\\^`\[\]]+', output)
                if url_match:
                    url = url_match.group(0)
                    # Add to sources if not already present
                    if not any(s.get('url') == url for s in log_data['content']['sources']):
                        log_data['content']['sources'].append({
                            "url": url,
                            "used": None,  # Will be updated later
                            "skip_reason": "",
                            "scraped_at": datetime.now().isoformat()
                        })
            
            # Check if this is a source selection/rejection event
            elif 'selected' in content.lower() or 'rejected' in content.lower():
                # Try to extract URL and reason
                url_match = re.search(r'https?://[^\s<>"{}|\\^`\[\]]+', output)
                if url_match:
                    url = url_match.group(0)
                    used = 'selected' in content.lower() or 'used' in content.lower()
                    
                    # Update or add the source
                    source_found = False
                    for source in log_data['content']['sources']:
                        if source['url'] == url:
                            source['used'] = used
                            if not used:
                                source['skip_reason'] = self._extract_skip_reason(output)
                            source_found = True
                            break
                    
                    if not source_found:
                        log_data['content']['sources'].append({
                            "url": url,
                            "used": used,
                            "skip_reason": self._extract_skip_reason(output) if not used else "",
                            "scraped_at": datetime.now().isoformat()
                        })
        
        # Handle scraped_data events
        elif data.get('type') == 'scraped_data':
            scraped_sites = data.get('scraped_sites', [])
            for site in scraped_sites:
                url = site.get('url')
                if url and not any(s.get('url') == url for s in log_data['content']['sources']):
                    log_data['content']['sources'].append({
                        "url": url,
                        "used": site.get('used', True),
                        "skip_reason": site.get('skip_reason', ''),
                        "title": site.get('title', ''),
                        "content_length": site.get('content_length', 0),
                        "scraped_at": datetime.now().isoformat()
                    })
        
        # Handle source updates
        elif data.get('type') == 'source_update':
            url = data.get('url')
            if url:
                source_found = False
                for source in log_data['content']['sources']:
                    if source['url'] == url:
                        source.update({
                            'used': data.get('used', source.get('used')),
                            'skip_reason': data.get('skip_reason', source.get('skip_reason', '')),
                            'title': data.get('title', source.get('title', '')),
                            'content_length': data.get('content_length', source.get('content_length', 0))
                        })
                        source_found = True
                        break
                
                if not source_found:
                    log_data['content']['sources'].append({
                        "url": url,
                        "used": data.get('used', False),
                        "skip_reason": data.get('skip_reason', ''),
                        "title": data.get('title', ''),
                        "content_length": data.get('content_length', 0),
                        "scraped_at": datetime.now().isoformat()
                    })
        
        # Handle curator decisions
        elif data.get('type') == 'curator_decisions':
            curator_decisions = data.get('decisions', {})
            log_data['content']['curator_decisions'].update(curator_decisions)
        
        else:
            # Update content section for other types of data
            log_data['content'].update(data)
            
        # Save updated log file
        with open(self.log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        logger.debug(f"Log entry written to: {self.log_file}")

    def _extract_skip_reason(self, text: str) -> str:
        """Extract skip reason from log text"""
        text_lower = text.lower()
        
        # Common skip reasons
        if 'too short' in text_lower or 'content too short' in text_lower:
            return "Content too short (less than 100 characters)"
        elif 'empty' in text_lower or 'no content' in text_lower:
            return "Empty or no content"
        elif 'error' in text_lower or 'failed' in text_lower:
            return "Scraping error or failed to load"
        elif 'timeout' in text_lower:
            return "Request timeout"
        elif 'low relevance' in text_lower or 'not relevant' in text_lower:
            return "Low relevance to query"
        elif 'duplicate' in text_lower:
            return "Duplicate content"
        elif 'access denied' in text_lower or 'forbidden' in text_lower:
            return "Access denied (403/401)"
        else:
            return "Other reason"


class Researcher:
    def __init__(self, query: str, report_type: str = "research_report"):
        self.query = query
        self.report_type = report_type
        # Generate unique ID for this research task
        self.research_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(query)}"
        # Initialize logs handler with research ID
        self.logs_handler = CustomLogsHandler(None, self.research_id)
        self.researcher = GPTResearcher(
            query=query,
            report_type=report_type,
            websocket=self.logs_handler
        )

    async def research(self) -> dict:
        """Conduct research and return paths to generated files"""
        await self.researcher.conduct_research()
        report = await self.researcher.write_report()
        
        # Generate the files
        sanitized_filename = sanitize_filename(f"task_{int(time.time())}_{self.query}")
        file_paths = await generate_report_files(report, sanitized_filename)
        
        # Get the JSON log path that was created by CustomLogsHandler
        json_relative_path = os.path.relpath(self.logs_handler.log_file)
        
        return {
            "output": {
                **file_paths,  # Include PDF, DOCX, and MD paths
                "json": json_relative_path
            }
        }

def sanitize_filename(filename: str) -> str:
    # Split into components
    prefix, timestamp, *task_parts = filename.split('_')
    task = '_'.join(task_parts)
    
    # Calculate max length for task portion
    max_task_length = 255 - len(os.getcwd()) - 24 - 5 - 10 - 6 - 5
    
    # Truncate task if needed (by bytes)
    truncated_task = ""
    byte_count = 0
    for char in task:
        char_bytes = len(char.encode('utf-8'))
        if byte_count + char_bytes <= max_task_length:
            truncated_task += char
            byte_count += char_bytes
        else:
            break

    # Reassemble and clean the filename
    sanitized = f"{prefix}_{timestamp}_{truncated_task}"
    return re.sub(r"[^\w-]", "", sanitized).strip()


async def handle_start_command(websocket, data: str, manager):
    json_data = json.loads(data[6:])
    (
        task,
        report_type,
        source_urls,
        document_urls,
        tone,
        headers,
        report_source,
        query_domains,
        mcp_enabled,
        mcp_strategy,
        mcp_configs,
    ) = extract_command_data(json_data)

    if not task or not report_type:
        print("❌ Error: Missing task or report_type")
        await websocket.send_json({
            "type": "logs",
            "content": "error", 
            "output": f"Missing required parameters - task: {task}, report_type: {report_type}"
        })
        return

    # Create logs handler with websocket and task
    logs_handler = CustomLogsHandler(websocket, task)
    # Initialize log content with query
    await logs_handler.send_json({
        "query": task,
        "sources": [],
        "context": [],
        "report": ""
    })

    sanitized_filename = sanitize_filename(f"task_{int(time.time())}_{task}")

    report = await manager.start_streaming(
        task,
        report_type,
        report_source,
        source_urls,
        document_urls,
        tone,
        websocket,
        headers,
        query_domains,
        mcp_enabled,
        mcp_strategy,
        mcp_configs,
    )
    report = str(report)
    file_paths = await generate_report_files(report, sanitized_filename)
    # Add JSON log path to file_paths
    file_paths["json"] = os.path.relpath(logs_handler.log_file)
    await send_file_paths(websocket, file_paths)


async def handle_human_feedback(data: str):
    feedback_data = json.loads(data[14:])
    print(f"Received human feedback: {feedback_data}")


async def handle_chat(websocket, data: str, manager):
    json_data = json.loads(data[4:])
    print(f"Received chat message: {json_data.get('message')}")
    await manager.chat(json_data.get("message"), websocket)

async def generate_report_files(report: str, filename: str) -> Dict[str, str]:
    pdf_path = await write_md_to_pdf(report, filename)
    docx_path = await write_md_to_word(report, filename)
    md_path = await write_text_to_md(report, filename)
    
    # === Append to persistent query_scraping_log.md ===
    try:
        log_path = Path("query_scraping_log.md")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Load sources from the JSON log created by CustomLogsHandler if available
        sources_info = []
        json_log_file = Path(f"outputs/{filename}.json")
        curator_decisions = {}
        
        if json_log_file.exists():
            with open(json_log_file, "r", encoding="utf-8") as jf:
                data = json.load(jf)
                query_text = data.get("content", {}).get("query", "")
                sources = data.get("content", {}).get("sources", [])
                curator_decisions = data.get("content", {}).get("curator_decisions", {})
                
                for src in sources:
                    url = src.get("url", "")
                    used = src.get("used")
                    
                    # Determine used status
                    if used is None:
                        used_flag = "Unknown"
                    elif used:
                        used_flag = "✅ Yes"
                    else:
                        used_flag = "✗ No"
                    
                    # Get curator decision
                    curator_info = curator_decisions.get(url, {})
                    curator_kept = curator_info.get('kept', None)
                    curator_reason = curator_info.get('reason', '')
                    
                    if curator_kept is None:
                        curator_status = "N/A"
                    elif curator_kept:
                        curator_status = "✅ Yes"
                    else:
                        curator_status = "✗ No"
                    
                    reason = src.get("skip_reason", "")
                    title = src.get("title", "")
                    content_length = src.get("content_length", "")
                    
                    sources_info.append((url, used_flag, curator_status, curator_reason, reason, title, content_length))
        else:
            query_text = filename
            sources_info = []
        
        # Create or append to the markdown log
        if not log_path.exists():
            with open(log_path, "w", encoding="utf-8") as logf:
                logf.write("# Query Scraping Log\n\n")
                logf.write("This file tracks all queries, websites checked, and their usage status.\n\n")
                logf.write("---\n\n")
        
        # Append new query section
        with open(log_path, "a", encoding="utf-8") as logf:
            logf.write(f"\n## Query: {query_text}\n\n")
            logf.write(f"**Timestamp:** {timestamp}\n\n")
            logf.write(f"**Total Sources Checked:** {len(sources_info)}\n\n")
            
            if sources_info:
                # Count statistics
                used_count = sum(1 for _, used, _, _, _, _, _ in sources_info if used == "✅ Yes")
                not_used_count = sum(1 for _, used, _, _, _, _, _ in sources_info if used == "✗ No")
                unknown_count = sum(1 for _, used, _, _, _, _, _ in sources_info if used == "Unknown")
                
                curator_kept_count = sum(1 for _, _, curator_status, _, _, _, _ in sources_info if curator_status == "✅ Yes")
                curator_rejected_count = sum(1 for _, _, curator_status, _, _, _, _ in sources_info if curator_status == "✗ No")
                curator_na_count = sum(1 for _, _, curator_status, _, _, _, _ in sources_info if curator_status == "N/A")
                
                logf.write(f"**Sources Used (Scraped Successfully):** {used_count}\n")
                logf.write(f"**Sources Skipped (Scraping Failed):** {not_used_count}\n")
                logf.write(f"**Sources Unknown:** {unknown_count}\n\n")
                logf.write(f"**LLM Curator Kept:** {curator_kept_count}\n")
                logf.write(f"**LLM Curator Rejected:** {curator_rejected_count}\n")
                logf.write(f"**LLM Curator N/A (Not Evaluated):** {curator_na_count}\n\n")
                
                # Write detailed table
                logf.write("### Detailed Source Information\n\n")
                logf.write("| # | URL | Scraped | LLM Curator | Title | Content Length | Scraping Skip Reason | Curator Rejection Reason |\n")
                logf.write("|---|-----|---------|-------------|-------|----------------|----------------------|--------------------------|\n")
                
                for idx, (url, used, curator_status, curator_reason, reason, title, content_length) in enumerate(sources_info, 1):
                    display_url = (url if len(url) <= 50 else url[:47] + "...") if url else "-"
                    display_title = (title if len(title) <= 30 else title[:27] + "...") if title else "-"
                    content_display = f"{content_length} chars" if content_length else "-"
                    display_curator_reason = (curator_reason if len(curator_reason) <= 40 else curator_reason[:37] + "...") if curator_reason else "-"
                    
                    logf.write(f"| {idx} | {display_url} | {used} | {curator_status} | {display_title} | {content_display} | {reason or '-'} | {display_curator_reason} |\n")
            else:
                logf.write("*No sources were checked for this query.*\n")
            
            logf.write("\n---\n")
        
        logger.info(f"Query scraping log updated: {log_path}")
        
    except Exception as e:
        logger.error(f"Failed to append query scraping log: {e}", exc_info=True)
    
    return {"pdf": pdf_path, "docx": docx_path, "md": md_path}


async def send_file_paths(websocket, file_paths: Dict[str, str]):
    await websocket.send_json({"type": "path", "output": file_paths})


def get_config_dict(
    langchain_api_key: str, openai_api_key: str, tavily_api_key: str,
    google_api_key: str, google_cx_key: str, bing_api_key: str,
    searchapi_api_key: str, serpapi_api_key: str, serper_api_key: str, searx_url: str
) -> Dict[str, str]:
    return {
        "LANGCHAIN_API_KEY": langchain_api_key or os.getenv("LANGCHAIN_API_KEY", ""),
        "OPENAI_API_KEY": openai_api_key or os.getenv("OPENAI_API_KEY", ""),
        "TAVILY_API_KEY": tavily_api_key or os.getenv("TAVILY_API_KEY", ""),
        "GOOGLE_API_KEY": google_api_key or os.getenv("GOOGLE_API_KEY", ""),
        "GOOGLE_CX_KEY": google_cx_key or os.getenv("GOOGLE_CX_KEY", ""),
        "BING_API_KEY": bing_api_key or os.getenv("BING_API_KEY", ""),
        "SEARCHAPI_API_KEY": searchapi_api_key or os.getenv("SEARCHAPI_API_KEY", ""),
        "SERPAPI_API_KEY": serpapi_api_key or os.getenv("SERPAPI_API_KEY", ""),
        "SERPER_API_KEY": serper_api_key or os.getenv("SERPER_API_KEY", ""),
        "SEARX_URL": searx_url or os.getenv("SEARX_URL", ""),
        "LANGCHAIN_TRACING_V2": os.getenv("LANGCHAIN_TRACING_V2", "true"),
        "DOC_PATH": os.getenv("DOC_PATH", "./my-docs"),
        "RETRIEVER": os.getenv("RETRIEVER", ""),
        "EMBEDDING_MODEL": os.getenv("OPENAI_EMBEDDING_MODEL", "")
    }


def update_environment_variables(config: Dict[str, str]):
    for key, value in config.items():
        os.environ[key] = value


async def handle_file_upload(file, DOC_PATH: str) -> Dict[str, str]:
    file_path = os.path.join(DOC_PATH, os.path.basename(file.filename))
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    print(f"File uploaded to {file_path}")

    document_loader = DocumentLoader(DOC_PATH)
    await document_loader.load()

    return {"filename": file.filename, "path": file_path}


async def handle_file_deletion(filename: str, DOC_PATH: str) -> JSONResponse:
    file_path = os.path.join(DOC_PATH, os.path.basename(filename))
    if os.path.exists(file_path):
        os.remove(file_path)
        print(f"File deleted: {file_path}")
        return JSONResponse(content={"message": "File deleted successfully"})
    else:
        print(f"File not found: {file_path}")
        return JSONResponse(status_code=404, content={"message": "File not found"})


async def handle_websocket_communication(websocket, manager):
    running_task: asyncio.Task | None = None

    def run_long_running_task(awaitable: Awaitable) -> asyncio.Task:
        async def safe_run():
            try:
                await awaitable
            except asyncio.CancelledError:
                logger.info("Task cancelled.")
                raise
            except Exception as e:
                logger.error(f"Error running task: {e}\n{traceback.format_exc()}")
                await websocket.send_json(
                    {
                        "type": "logs",
                        "content": "error",
                        "output": f"Error: {e}",
                    }
                )

        return asyncio.create_task(safe_run())

    try:
        while True:
            try:
                data = await websocket.receive_text()
                
                if data == "ping":
                    await websocket.send_text("pong")
                elif running_task and not running_task.done():
                    logger.warning(
                        f"Received request while task is already running. Request data preview: {data[: min(20, len(data))]}..."
                    )
                    websocket.send_json(
                        {
                            "types": "logs",
                            "output": "Task already running. Please wait.",
                        }
                    )
                elif data.startswith("start"):
                    running_task = run_long_running_task(
                        handle_start_command(websocket, data, manager)
                    )
                elif data.startswith("human_feedback"):
                    running_task = run_long_running_task(handle_human_feedback(data))
                elif data.startswith("chat"):
                    running_task = run_long_running_task(
                        handle_chat(websocket, data, manager)
                    )
                else:
                    print("Error: Unknown command or not enough parameters provided.")
            except Exception as e:
                print(f"WebSocket error: {e}")
                break
    finally:
        if running_task and not running_task.done():
            running_task.cancel()

def extract_command_data(json_data: Dict) -> tuple:
    return (
        json_data.get("task"),
        json_data.get("report_type"),
        json_data.get("source_urls"),
        json_data.get("document_urls"),
        json_data.get("tone"),
        json_data.get("headers", {}),
        json_data.get("report_source"),
        json_data.get("query_domains", []),
        json_data.get("mcp_enabled", False),
        json_data.get("mcp_strategy", "fast"),
        json_data.get("mcp_configs", []),
    )