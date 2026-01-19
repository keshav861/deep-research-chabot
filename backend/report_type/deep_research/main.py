from gpt_researcher import GPTResearcher
from backend.utils import write_md_to_pdf,write_md_to_word, write_text_to_md
import asyncio


async def main(task: str):
    # Progress callback
    def on_progress(progress):
        print(f"Depth: {progress.current_depth}/{progress.total_depth}")
        print(f"Breadth: {progress.current_breadth}/{progress.total_breadth}")
        print(f"Queries: {progress.completed_queries}/{progress.total_queries}")
        if progress.current_query:
            print(f"Current query: {progress.current_query}")
    
    # Initialize researcher with deep research type
    researcher = GPTResearcher(
        query=task,
        report_type="deep",  # This will trigger deep research
    )
    
    # Run research with progress tracking
    print("Starting deep research...")
    context = await researcher.conduct_research(on_progress=on_progress)
    print("\nResearch completed. Generating report...")
    
    # Generate the final report
    report = await researcher.write_report()
    
    # Save in multiple formats with proper table and code styling (similar to multi-modal)
    await write_text_to_md(report, "deep_research_report")  # raw markdown
    await write_md_to_word(report, "deep_research_report")  # docx version
    await write_md_to_pdf(report, "deep_research_report")   # pdf version with styling
    
    print(f"\nFinal Report Generated in MD, DOCX, and PDF formats:\n{report}")

if __name__ == "__main__":
    query = "What are the most effective ways for beginners to start investing?"
    asyncio.run(main(query))