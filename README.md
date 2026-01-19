# Deep Researcher

An advanced AI-powered research and reporting platform that automates the process of gathering, analyzing, and synthesizing information from both web and local sources. Built with **FastAPI** for backend services and a lightweight **HTML/JS frontend**, it delivers detailed, factual research reports with proper citations for academic, business, and personal use cases.

---

## 1. Architecture Overview

The system is modular and organized into the following components:

- **Backend** (`backend/`): FastAPI-based REST and WebSocket APIs, report generation, and static file serving.
- **Core Research Engine** (`gpt_researcher/`): Retrieval, scraping, LLM orchestration, and utility modules.
- **Frontend** (`frontend/`): User interface for initiating research and interacting with agents.
- **Evaluation Framework** (`evals/`): Scripts to benchmark and assess model outputs.

**Key Interactions:**
- Research requests are sent from the frontend to the backend.
- The backend orchestrates retrieval (via the active retriever), scraping, and LLM-based synthesis.
- Results are streamed back to the frontend via WebSockets.

**Dependencies:**
- **FastAPI**, **Uvicorn** for API/WebSocket serving.
- **BeautifulSoup4**, **PyMuPDF** for scraping.
- **Azure OpenAI** for LLM-based synthesis.
---

## 2. Key Features and Active Components

### Active Components
- **Retriever**: `DuckDuckGoRetriever` (no LangChain used for retrieval).
  - Aggregates search results from multiple sources via DuckDuckGo's public endpoint.
- **Scraper**: `BeautifulSoupScraper` (default active in this environment).
  - Performs static HTML parsing and content extraction.
- **Report Types**: Short summary, Resource Report, Detailed reports, Deep Research and Multi agent Report.
- **Real-time streaming** of research results via WebSockets.
---

## 3. Installation and Setup Instructions

### Prerequisites
- Python 3.10+
- `pip` package manager

### Steps
1. **Clone Repository**  
   ```bash
   git clone <repository-url>
   cd market-intelligence
   ```
   or
   <br>
   ```bash
   download zip from GitLab and unzip
   cd market-intelligence
   ```

2. **Create Environment File**  
   Create a `.env` file in the root directory:
   ```env
   OPENAI_API_VERSION=<your-azure-openai-api-version>
   AZURE_OPENAI_API_VERSION=<your-azure-openai-api-version>
   AZURE_OPENAI_ENDPOINT=<your-azure-openai-endpoint>
   AZURE_OPENAI_API_KEY=<your-azure-openai-key>

   # Model deployments
   EMBEDDING=azure_openai:text-embedding-3-large
   FAST_LLM=azure_openai:gpt-5-chat
   FAST_TOKEN_LIMIT=10000
   SMART_LLM=azure_openai:gpt-5-chat
   SMART_TOKEN_LIMIT=10000
   STRATEGIC_LLM=azure_openai:gpt-5-chat
   STRATEGIC_TOKEN_LIMIT=10000

   # Search provider
   RETRIEVER=duckduckgo
   DOC_PATH=./mydocs
   ```

3. **Install Dependencies**  
   ```bash
   pip install -r requirements.txt
   ```

4. **Activate Alternative Retrievers/Scrapers**  
   - Set `RETRIEVER` or `SCRAPER` in `.env` or configuration files.
   - Example: `SCRAPER=bs` to enable `BeautifulSoupScraper`.

---

## 4. Usage Instructions

### Start Backend
```bash
uvicorn main:app --reload --port 3001
```

### Start Frontend
- Static frontend is served automatically by the backend at:
  [http://localhost:3001](http://localhost:3001)

### Run a Research Request
1. Open the frontend in your browser.
2. Enter your research query.
3. Select report type (Short/Resource/Detailed/Multi-agent/Deep Research) and source (Web/My Documents).
4. Wait for streamed results and export them in PDF, Word, or Markdown.

**Result Storage:**  
Reports are stored in the output directory specified in configuration.

---

## 5. Diagrams and Visualizations

### Project Flow Diagram
![Project Flow](docs/process%20map%20final.png)  
Shows the high-level flow from query input to report generation.

### End-to-End Lifecycle
![End-to-End Lifecycle](docs/lifecycle.png)  
Visualizes the complete lifecycle from retrieval to final report delivery.

---

## 6. Report Types Overview

Below is a detailed overview of the **4 report types currently available in the frontend**, including their purpose, use case, operational details, and the exact English-language prompts sent to the AI.

### **1. research_report** — *Summary - Short and fast (~2 min)*
**Purpose:**
Generate a standard research report summarizing findings from online and document-based sources for a given query.

**Use Case:**
Use when a concise, well‑structured report is required without extended subtopic breakdowns or deep iterative exploration.

**Operational Details:**
- Handled by `GPTResearcher` with `report_type="research_report"`.
- Executes a single-phase research process (`conduct_research` → `write_report`).
- Uses retrievers, scrapers, and summarizers in `gpt_researcher/skills/researcher.py`.

**Prompt Text Sent to AI:**
> Using the above information, answer the following query or task: "{question}" in a detailed report --
> The report should focus on the answer to the query, should be well structured, informative, in-depth, and comprehensive, with facts and numbers if available and at least 1000 words. You should strive to write the report as long as you can using all relevant and necessary information provided.
> Please follow all of the following guidelines in your report:
> - You MUST determine your own concrete and valid opinion based on the given information. Do NOT defer to general and meaningless conclusions.
> - You MUST write the report with markdown syntax and APA format.
> - Use markdown tables when presenting structured data or comparisons to enhance readability.
> - You MUST prioritize the relevance, reliability, and significance of the sources you use. Choose trusted sources over less reliable ones.
> - You must also prioritize new articles over older articles if the source can be trusted.
> - You MUST NOT include a table of contents. Start from the main report body directly.
> - Use in-text citation references in APA format and make it with markdown hyperlink placed at the end of the sentence or paragraph that references them like this: ([in-text citation](url)).
> - Don't forget to add a reference list at the end of the report in APA format and full URL links without hyperlinks.
> - You MUST write all used source URLs at the end of the report as references (no duplicates), hyperlinked in the format `[url website](url)`, and also hyperlink them inline where relevant.
> - Write the report in the requested tone and in English.
> Assume that the current date is *{today's date}*.

---

### **2. detailed_report** — *Detailed - In depth and longer (~5 min)*
**Purpose:**
Produce a long-form report with hierarchical structure, subtopics, and comprehensive coverage.

**Use Case:**
When a topic needs to be broken down into multiple subtopics, each explored with its own research cycle, and compiled into a single cohesive document.

**Operational Details:**
- Implemented in `backend/report_type/detailed_report/detailed_report.py`.
- Steps:
  1. Generate an initial `research_report` on the main query.
  2. Extract subtopics from the initial summary.
  3. For each subtopic, run a `subtopic_report` researcher and avoid regenerating already covered headers.
  4. Merge subtopic sections into a cohesive document.

**Prompt Text Sent to AI (per subtopic):**
> Context: "{context}"
> Using the latest information available, construct a detailed report on the subtopic **{current_subtopic}** under the main topic **{main_topic}**.
> - Limit subsections to a maximum of {max_subsections}.
> - Focus on being well-structured, informative, in-depth, with facts and numbers if available.
> - Use markdown syntax and APA format.
> - Include markdown hyperlinks for sources inline.
> - Ensure uniqueness: do not repeat or overlap with existing sections; highlight differences if similar.
> - No introduction, conclusion, or summary in subtopic sections.
> - Minimum {total_words} words, in the requested tone, in English.

---

### **3. resource_report** — *Resource Report*
**Purpose:**
Generate a bibliography recommendation report, analyzing each source’s relevance and contribution to the research question.

**Use Case:**
When the goal is to identify and evaluate resources rather than produce a narrative synthesis.

**Operational Details:**
- Implemented in backend as `generate_resource_report_prompt`.
- Produces structured entries for each recommended resource with relevance analysis.

**Prompt Text Sent to AI:**
> """{context}"""
> Based on the above information, generate a bibliography recommendation report for the following question or topic: "{question}".
> The report should provide a detailed analysis of each recommended resource, explaining how each source can contribute to finding answers to the research question.
> Focus on the relevance, reliability, and significance of each source.
> Ensure that the report is well-structured, informative, in-depth, and follows Markdown syntax.
> Use markdown tables and other formatting features when appropriate to organize and present information clearly.
> Include relevant facts, figures, and numbers whenever available.
> Minimum length: 1000 words.
> You MUST include all relevant source URLs, hyperlinked in the format `[url website](url)`.
> If using non-web sources, list their document names instead (no duplicates).
> Write the report in English.

---

### **4. deep** — *Deep Research*
**Purpose:**
Perform recursive, multi-branch deep research to explore a topic in maximum breadth and depth.

**Use Case:**
When exhaustive coverage is required across multiple dimensions of a topic.

**Operational Details:**
- Managed by `DeepResearchSkill` in `gpt_researcher/skills/deep_research.py`.
- Uses parameters for breadth, depth, and concurrency to control research branching.

**Prompt Text Sent to AI:**
> Using the following hierarchically researched information and citations:
> "{context}"
> Write a comprehensive research report answering the query: "{question}"
> The report should:
> 1. Synthesize information from multiple levels of research depth
> 2. Integrate findings from various research branches
> 3. Present a coherent narrative that builds from foundational to advanced insights
> 4. Maintain proper citation of sources throughout
> 5. Be well-structured with clear sections and subsections
> 6. Have a minimum length of 2000 words
> 7. Follow APA format with markdown syntax
> 8. Use markdown tables, lists, and other formatting features when presenting comparative data, statistics, or structured information
> Additional requirements:
> - Prioritize insights from deeper research levels
> - Highlight connections between different research branches
> - Include relevant statistics, data, and concrete examples
> - You MUST determine your own concrete and valid opinion based on the given information
> - Prioritize relevance, reliability, and significance of sources; prefer newer trusted sources
> - Use in-text citation references in APA format with markdown hyperlinks at the end of the sentence or paragraph like this: ([in-text citation](url))
> - Write in English and in the requested tone
> - Include all used source URLs at the end (no duplicates), hyperlinked in `[url website](url)` format, and inline where relevant
> Assume the current date is *{today's date}*.

---

### **5. multi_agent_report** — *Collaborative Multi-Agent Research*
**Purpose:**
Leverage a team of specialized AI agents—each with distinct expertise and roles—to collaboratively produce a comprehensive, multi‑perspective report.

**Use Case:**
Ideal for complex, interdisciplinary topics where multiple viewpoints, domain expertise, and iterative refinement are essential. Best suited when depth, accuracy, and synthesis across different knowledge areas are required.

**Operational Details:**
- Implemented in `backend/report_type/multi_agent_report/multi_agent_report.py` and orchestrated via the `multi_agents/` framework.
- Workflow:
 1. **Orchestrator Agent** — Interprets the main query, defines objectives, and assigns tasks to domain‑specific agents.
 2. **Domain Specialist Agents** — Examples include:
    - Researcher Agents (gather raw information from trusted sources)
    - Analyst Agents (interpret and contextualize findings)
    - Writer Agents (draft structured, coherent sections)
    - Reviewer & Reviser Agents (fact‑check, ensure clarity, resolve inconsistencies)
    - Editor & Publisher Agents (final formatting, style compliance, and export)
 3. Agents communicate and exchange intermediate outputs, refining content iteratively.
 4. Final report is merged, validated, and formatted according to APA and markdown standards.

**Unique Features & Advantages:**
- **Parallel Expertise:** Multiple agents work concurrently, drastically reducing turnaround for large‑scale research.
- **Specialization:** Each agent is optimized for its role, ensuring higher quality in research, analysis, writing, and review.
- **Iterative Refinement:** Continuous feedback loops between agents improve accuracy, eliminate contradictions, and enhance readability.
- **Scalability:** Easily extended with new agent types for emerging domains.

**Example Scenarios:**
- A policy paper requiring legal, economic, and environmental perspectives.
- A technical whitepaper merging inputs from software engineering, cybersecurity, and UX design experts.
- A market intelligence report combining financial analysis, competitor benchmarking, and consumer behavior insights.

**Prompt Text Sent to AI (simplified illustration):**
> Main Query: "{question}"
> Assigned Tasks: Distributed among relevant agents with individual prompts tailored to their domain and role.
> Each agent must:
> - Conduct role‑specific research or analysis
> - Document sources in APA format with markdown hyperlinks
> - Collaborate with other agents to resolve discrepancies
> - Return outputs for final synthesis and editing
> The orchestrator compiles all sections into a unified, coherent report following the requested tone, structure, and style.
