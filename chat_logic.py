from typing import AsyncGenerator
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

# --- System Prompt ---
CHAT_SYSTEM_PROMPT = """You are the AI Legal Strategos. You have already generated a comprehensive 'War Game Directive' for the user. Your current task is to answer follow-up questions concisely.

Core Directives:
- Your primary source of information is the conversation history and the original directive.
- Maintain your persona: clinical, brutally honest, and relentlessly focused on the user's strategic objectives.
- Keep responses concise: 3-4 lines maximum.
"""

def build_chat_prompt(query: str, context: str) -> str:
    """Builds the final prompt for the chat LLM call."""
    return f"{CHAT_SYSTEM_PROMPT}\n\n[RETRIEVED CONTEXT]\n{context}\n\n[USER QUERY]\n{query}"

async def stream_chat_response(query: str, conversation_id: str, SESSION_STORE) -> AsyncGenerator[str, None]:
    # Retrieve conversation context
    context_data = SESSION_STORE.get(conversation_id, {})
    context_str = context_data.get("case_facts", "") + "\nPrevious AI Responses:\n"
    for entry in context_data.get("history", []):
        context_str += f"- {entry}\n"

    prompt = build_chat_prompt(query, context_str)

    # Initialize LangChain Gemini Chat model
    chat_model = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.2, max_output_tokens=400)

    try:
        # Generate response
        response = chat_model([HumanMessage(content=prompt)])
        response_text = response.content.strip()
    except Exception as e:
        yield f"[ERROR] Gemini API call failed: {e}\n"
        return

    # Save to ephemeral session store
    context_data.setdefault("history", []).append(response_text)
    SESSION_STORE[conversation_id] = context_data

    # Stream concise response
    yield response_text
