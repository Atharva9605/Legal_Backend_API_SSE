from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from reflexion_graph_stream import stream_reflexion_graph
from dotenv import load_dotenv
import asyncio

load_dotenv()

app = FastAPI(title="Legal Advisor - War Game Directive Streamer")

# ✅ Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # You can replace "*" with your Lovable frontend URL for stricter security
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return HTMLResponse(
        "<h3>Legal Advisor War Game Directive Streamer</h3>"
        "<p>POST JSON to <code>/stream</code> with <code>{\"case_facts\":\"...\"}</code> to stream an 11-part directive tailored to the facts.</p>"
        "<p>Or GET <code>/stream?prompt=... (urlencoded)</code></p>"
    )

@app.post("/stream")
async def stream_post(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    case_facts = body.get("case_facts") or body.get("prompt") or ""
    if not case_facts:
        raise HTTPException(status_code=400, detail="Missing 'case_facts' in request body")

    async def event_gen():
        async for chunk in stream_reflexion_graph(case_facts):
            yield f"data: {chunk}\n\n"
            await asyncio.sleep(0)

    return StreamingResponse(event_gen(), media_type="text/event-stream")

@app.get("/stream")
async def stream_get(prompt: str = None):
    if not prompt:
        raise HTTPException(
            status_code=400,
            detail="Provide ?prompt=... or use POST with JSON {'case_facts': '...'}"
        )

    async def event_gen():
        async for chunk in stream_reflexion_graph(prompt):
            yield f"data: {chunk}\n\n"
            await asyncio.sleep(0)

    return StreamingResponse(event_gen(), media_type="text/event-stream")
