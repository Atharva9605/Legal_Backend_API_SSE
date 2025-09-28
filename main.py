from dotenv import load_dotenv
load_dotenv()

import os
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import shortuuid

from chat_logic import stream_chat_response
from reflexion_graph_stream import stream_reflexion_graph

# --- Ephemeral in-memory store for conversation context ---
SESSION_STORE = {}

app = FastAPI(title="Legal Advisor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return HTMLResponse(
        """
        <h3>Legal Advisor API</h3>
        <p><b>1. Generate Directive:</b> POST to <code>/generate_directive</code> with JSON <code>{"case_facts":"..."}</code> to start.</p>
        <p><b>2. Chat:</b> POST to <code>/chat</code> with JSON <code>{"query":"...", "conversation_id": "..."}</code> to have a conversation.</p>
        """
    )

@app.post("/generate_directive")
async def generate_directive(request: Request, background_tasks: BackgroundTasks):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    case_facts = body.get("case_facts")
    if not case_facts:
        raise HTTPException(status_code=400, detail="Missing 'case_facts' in request body")

    new_conversation_id = shortuuid.uuid()
    SESSION_STORE[new_conversation_id] = {"case_facts": case_facts, "history": []}

    async def directive_generator():
        # Send conversation ID first
        yield f"data: [CONVERSATION_ID] {new_conversation_id}\n\n"

        # Stream 11 parts separately
        async for chunk in stream_reflexion_graph(case_facts):
            yield f"data: {chunk}\n\n"
            await asyncio.sleep(0.001)

        yield f"data: [INFO] Directive generation complete.\n\n"

    return StreamingResponse(directive_generator(), media_type="text/event-stream")


@app.post("/chat")
async def chat(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    query = body.get("query")
    conversation_id = body.get("conversation_id")
    if not all([query, conversation_id]):
        raise HTTPException(status_code=400, detail="Missing 'query' or 'conversation_id'")

    async def sse_event_wrapper(generator):
        async for chunk in generator:
            yield f"data: {chunk}\n\n"
            await asyncio.sleep(0.001)

    return StreamingResponse(
        sse_event_wrapper(stream_chat_response(query, conversation_id, SESSION_STORE)),
        media_type="text/event-stream"
    )
