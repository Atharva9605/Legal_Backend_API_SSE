# execute_tools.py
import json
from typing import List, AsyncGenerator
from dotenv import load_dotenv
load_dotenv()

# We use TavilySearch if available; otherwise fallback to a stub.
try:
    from langchain_tavily import TavilySearch
    HAVE_TAVILY = True
except Exception:
    HAVE_TAVILY = False

if HAVE_TAVILY:
    tavily = TavilySearch(
        topic="news",
        search_depth="advanced",
        include_answer="advanced",
        include_raw_content="text",
        country="india",
        include_domains=["https://indiankanoon.org/", "https://www.indiacode.nic.in/"]
    )
else:
    tavily = None

import asyncio

async def run_search_queries(queries: List[str]) -> AsyncGenerator[tuple, None]:
    """
    For each query in queries, yields (query, text_result)
    This is async so calling code can stream results as they arrive.
    """
    for q in queries:
        try:
            if tavily is not None:
                # tavily.invoke is synchronous; run in threadpool to avoid blocking
                loop = asyncio.get_event_loop()
                res = await loop.run_in_executor(None, lambda: tavily.invoke(q))
                # res may be complex; stringify safely
                try:
                    result_text = json.dumps(res)[:4000]  # truncate to avoid huge payloads
                except Exception:
                    result_text = str(res)[:4000]
            else:
                # stub result for local testing
                result_text = f"(tavily stub) Results for query: {q}"
        except Exception as e:
            result_text = f"(search error) {e}"
        yield q, result_text
        await asyncio.sleep(0.01)
