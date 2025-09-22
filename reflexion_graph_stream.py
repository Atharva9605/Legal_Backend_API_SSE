# reflexion_graph_stream.py
from reflexion_graph_module import app as compiled_app
import asyncio

async def stream_reflexion_graph(case_facts: str):
    """
    Delegates to compiled_app.stream_invoke which yields small text pieces
    (these pieces are already line-oriented so the Flask/FASTAPI layer can wrap them in SSE).
    """
    try:
        async for piece in compiled_app.stream_invoke(case_facts):
            yield piece
            await asyncio.sleep(0)
    except Exception as e:
        yield f"[ERROR] {e}\n"
