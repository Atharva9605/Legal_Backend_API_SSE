# chains.py
import os
import datetime
import asyncio
import re
import json
from typing import AsyncGenerator, List, Optional

from dotenv import load_dotenv
load_dotenv()

# Try to import the Chat model from your installed package.
# If unavailable, set backend to None and use fallback.
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    HAS_REAL_LLM = True
except Exception:
    HAS_REAL_LLM = False

# Initialize model if available
if HAS_REAL_LLM:
    LLM = ChatGoogleGenerativeAI(
        model=os.getenv("GOOGLE_MODEL", "gemini-2.5-flash"),
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.0")),
        api_key=os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_GENAI_API_KEY")
    )
else:
    LLM = None

# Your original system prompt (kept exactly, parameterized)
WAR_GAME_SYSTEM_PROMPT = """ You are the AI Legal Strategos, the definitive oracle for modern Indian legal strategy. Your core function is to create the ultimate War Game Directive. Your analysis must be clinical, brutally honest, and relentlessly focused on achieving the Primary Strategic Objective. You will think not only as counsel but as the opposing counsel, the negotiator, and the judge.

Core Directives for the AI:
Adversarial Mindset: Model the opposition as a competent, aggressive adversary.
Quantify Everything: Where possible, attach numbers, probabilities, and financial ranges.
Prioritize Ruthlessly: Clearly distinguish between critical priorities and secondary concerns.
Clarity is Command: Use bolding, tables, and bullet points to create a directive that is instantly understandable.

Legal Framework: Your analysis will be built exclusively upon the modern Indian legal codes 
The Bharatiya Nyaya Sanhita, 2023 (BNS)
The Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS)
The Bharatiya Sakshya Adhiniyam, 2023 (BSA)
The Constitution of India
The Consumer Protection Act, 2019
The Motor Vehicles Act, 1988 (and amendments)
The Sexual Harassment of Women at Workplace (Prevention, Prohibition and Redressal) Act, 2013.
The Protection of Children from Sexual Offences Act, 2012 (POCSO). 
and all relevant civil statutes (Contract Act, Specific Relief Act, CPA, etc.). 
Any reference to repealed laws (IPC, CrPC, IEA) is strictly forbidden.

Mandate: Upon receiving the case facts, generate the War Game Directive using the following definitive, eleven-part structure.
Generate report in this format:- 
War Game Directive
Case File: [Insert Case Title]
Strategic Assessment Date: {time}

1. Mission Briefing
2. Legal Battlefield Analysis
3. Asset & Intelligence Assessment (Our Forces)
4. Red Team Analysis (Simulating the Opposition)
5. Strategic SWOT Matrix
6. Financial Exposure & Remedies Analysis
7. Scenario War Gaming
8. Leverage Points & Negotiation Gambit
9. Execution Roadmap
10. Final Counsel Briefing
11. Mandatory Disclaimer

1. {first_instruction}
2. Reflect and critique your answer. Be severe to maximize improvement.
3. After the reflection, **list 1-3 search queries separately** for researching improvements. Do not include them inside the reflection.
"""

# Helper: build the per-part prompt (we call this for each of 11 parts).
def build_part_prompt(case_facts: str, part_number: int, time: str, first_instruction: str):
    """
    The LLM is asked to return three clearly delimited sections:
      ---THOUGHTS---  (streamable internal reasoning)
      ---SEARCH_QUERIES---  (JSON array or newline list of up to 3 queries)
      ---DELIVERABLE---  (the final text for this part)
    We will parse by those markers.
    """
    part_header = f"PART {part_number} — Please produce only the THOUGHTS, SEARCH_QUERIES, and DELIVERABLE for this single numbered part.\n"
    system = WAR_GAME_SYSTEM_PROMPT.format(time=time, first_instruction=first_instruction)
    instructions = (
        part_header +
        "\nUse the case facts below. Format your response exactly with these markers:\n"
        "----THOUGHTS----\n"
        "(Write step-by-step reasoning that justifies the deliverable for this part. Keep it concise — 2-6 sentences. This is internal reasoning; stream it first.)\n"
        "----SEARCH_QUERIES----\n"
        "(List 0-3 short search queries (as a JSON array or newline-separated) that would help verify or strengthen the deliverable.)\n"
        "----DELIVERABLE----\n"
        "(Produce the content for this part of the War Game Directive — final, clear, actionable, ~100-250 words depending on part complexity.)\n\n"
    )
    prompt = f"{system}\n\n{instructions}\nCASE FACTS:\n{case_facts}\n\nNow produce the three sections for PART {part_number} only."
    return prompt

# Simple parser to extract sections
_SECTION_RE = re.compile(r"----THOUGHTS----\s*(.*?)\s*----SEARCH_QUERIES----\s*(.*?)\s*----DELIVERABLE----\s*(.*)", re.S | re.I)

def parse_model_sections(raw_text: str):
    """
    Returns tuple (thoughts, queries_list, deliverable)
    If parser fails, returns (raw_text, [], "")
    """
    m = _SECTION_RE.search(raw_text)
    if not m:
        # Try fallback: attempt to split by markers without exact lines
        parts = re.split(r"----THOUGHTS----|----SEARCH_QUERIES----|----DELIVERABLE----", raw_text, flags=re.I)
        if len(parts) >= 4:
            thoughts = parts[1].strip()
            queries_raw = parts[2].strip()
            deliverable = parts[3].strip()
            queries = try_parse_queries(queries_raw)
            return thoughts, queries, deliverable
        # As a last resort, return whole text as deliverable
        return "", [], raw_text.strip()
    thoughts = m.group(1).strip()
    queries_raw = m.group(2).strip()
    deliverable = m.group(3).strip()
    queries = try_parse_queries(queries_raw)
    return thoughts, queries, deliverable

def try_parse_queries(raw: str) -> List[str]:
    # Try JSON first
    try:
        cand = raw.strip()
        if cand.startswith("["):
            parsed = json.loads(cand)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed][:3]
    except Exception:
        pass
    # split lines and commas
    lines = [line.strip("- ").strip() for line in raw.splitlines() if line.strip()]
    if len(lines) > 0:
        # sometimes model returns one comma-separated line
        if len(lines) == 1 and "," in lines[0]:
            pieces = [p.strip() for p in lines[0].split(",") if p.strip()]
            return pieces[:3]
        return lines[:3]
    # nothing
    return []

# The async generator that orchestrates parts, LLM calls and tool executions
async def generate_full_directive_stream(case_facts: str, first_instruction: Optional[str] = None) -> AsyncGenerator[str, None]:
    """
    Yields strings representing small pieces to be streamed (each will be sent as SSE data lines).
    Sequence for each part:
      - header line "PART n"
      - LLM THOUGHTS lines (streamed)
      - (if any) SEARCH_QUERIES lines
      - TAVILY results streamed (each result chunk)
      - DELIVERABLE lines (streamed)
    """
    if first_instruction is None:
        first_instruction = "User will give you all info about the case. Analyse it thoroughly and explain each and every point in detail. Highlight important points."

    now = datetime.datetime.now().isoformat()
    total_parts = 11

    for part in range(1, total_parts + 1):
        header = f"=== PART {part} ===\n"
        yield header

        # Build prompt for this specific part
        part_prompt = build_part_prompt(case_facts, part, now, first_instruction)

        # Call LLM (sync or async) and get raw text
        raw = None
        if LLM is not None:
            try:
                # prefer .invoke or .generate depending on package
                if hasattr(LLM, "invoke"):
                    resp = LLM.invoke(part_prompt)
                    raw = str(resp)
                elif hasattr(LLM, "generate"):
                    resp = LLM.generate([{"role": "user", "content": part_prompt}])
                    # try to obtain text safely
                    gens = getattr(resp, "generations", None)
                    if gens and len(gens) > 0:
                        cand = gens[0][0]
                        raw = getattr(cand, "text", str(cand))
                    else:
                        raw = str(resp)
                else:
                    # fallback call
                    raw = str(LLM(part_prompt))
            except Exception as e:
                raw = f"[LLM ERROR] {e}"
        else:
            # fallback dummy output
            dummy_thoughts = f"(internal reasoning placeholder for part {part})"
            dummy_queries = [f"{case_facts.split('.')[0][:80]} structural defect law India"]  # 1 sample
            dummy_deliverable = f"(Deliverable placeholder for part {part} based on the facts.)"
            # assemble with markers so parser works
            raw = f"----THOUGHTS----\n{dummy_thoughts}\n----SEARCH_QUERIES----\n{json.dumps(dummy_queries)}\n----DELIVERABLE----\n{dummy_deliverable}"

        # Parse into sections
        thoughts, queries, deliverable = parse_model_sections(raw)

        # Stream THOUGHTS (line by line)
        if thoughts:
            yield "[THOUGHTS-BEGIN]\n"
            for line in str(thoughts).splitlines():
                yield f"{line}\n"
                await asyncio.sleep(0.01)
            yield "[THOUGHTS-END]\n"
        else:
            yield "[THOUGHTS: none]\n"

        # Stream SEARCH_QUERIES and then execute via execute_tools (which will run Tavily)
        if queries:
            yield "[SEARCH_QUERIES]\n"
            for q in queries:
                yield f"- {q}\n"
                await asyncio.sleep(0.005)
            # Import execute_tools here to avoid circular import at module level
            try:
                from execute_tools import run_search_queries  # updated helper below
                # run_search_queries returns an async generator of (query, result_text)
                async for q, res_text in run_search_queries(queries):
                    # stream each query result header + body
                    yield f"[TOOL-RESULT-BEGIN] {q}\n"
                    for line in res_text.splitlines():
                        yield f"{line}\n"
                        await asyncio.sleep(0.005)
                    yield f"[TOOL-RESULT-END] {q}\n"
            except Exception as e:
                # if execute_tools isn't available or errors, stream an error
                yield f"[TOOL-ERROR] {e}\n"
        else:
            yield "[SEARCH_QUERIES: none]\n"

        # Stream DELIVERABLE (line by line)
        if deliverable:
            yield "[DELIVERABLE-BEGIN]\n"
            for line in str(deliverable).splitlines():
                yield f"{line}\n"
                await asyncio.sleep(0.01)
            yield "[DELIVERABLE-END]\n"
        else:
            yield "[DELIVERABLE: none]\n"

        # Small separator between parts
        yield "\n"
        await asyncio.sleep(0.05)

    # Final overall wrap
    yield "[WAR-GAME-DIRECTIVE-COMPLETE]\n"
