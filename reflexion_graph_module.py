# reflexion_graph_module.py
from chains import generate_full_directive_stream

class ReflexionGraphApp:
    """thin wrapper exposing stream_invoke and invoke methods used by rest layer"""

    def __init__(self):
        pass

    def invoke(self, case_facts: str):
        # synchronous convenience: run the async generator fully and join text
        import asyncio
        parts = []
        async def collect():
            async for piece in generate_full_directive_stream(case_facts):
                parts.append(piece)
        asyncio.run(collect())
        return "".join(parts)

    async def stream_invoke(self, case_facts: str):
        # directly yield from generator
        async for piece in generate_full_directive_stream(case_facts):
            yield piece

# singleton used by other modules
app = ReflexionGraphApp()
