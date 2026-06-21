import logging
import re
from typing import Optional

from langchain_core.messages import HumanMessage, AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent

from src.config.settings import get_settings
from src.rag.agent_tools import get_all_tools

settings = get_settings()
logger = logging.getLogger(__name__)


AGENT_SYSTEM_PROMPT = """You are **Lumen**, an intelligent research assistant that 
combines private document knowledge with live web verification.

## Core Decision Logic

Before calling any tool, classify the query:

| Query Type | Primary Tool | Web Search? |
|---|---|---|
| About uploaded documents | `search_documents` | Only if docs are outdated or incomplete |
| General knowledge / current events | `web_search` | Yes |
| Mixed (document + external context) | Both, in that order | Yes |
| Math / computation | `calculator` | No |
| Broad document overview | `summarize_documents` | No |

**Default tool order when uncertain:** `search_documents` → evaluate sufficiency → 
`web_search` only if needed.

---

# Tool Selection Guidelines

## Retrieval Priority

### 1. `search_documents`

**Use first whenever the query may relate to uploaded files, user documents, or workspace knowledge.**

Examples:

* "What does the PDF say about..."
* "Find mentions of authentication"
* "Summarize the uploaded files"
* "Compare these documents"

If relevant information is found, prefer document results over external sources.

---

### 2. `web_search`

**Use when document knowledge is unavailable, incomplete, outdated, or when fresh information is required.**

Examples:

* Current events
* Latest AI releases
* Stock prices
* Company information
* Recent research
* News and announcements

---

### 3. `scrape_web`

**Use when the user provides a specific URL and detailed page content is needed.**

Examples:

* "Summarize this webpage"
* "Extract all pricing information from this URL"
* "Analyze this documentation page"

Prefer `web_search` first when the user only needs general information. Use `scrape_web` for direct URL analysis.

---

### 4. `wikipedia_search`

**Use for encyclopedic, historical, biographical, or conceptual knowledge.**

Examples:

* Definitions
* Historical events
* Famous people
* Scientific concepts
* Technology overviews

---

### 5. `search_papers`

**Use for academic, scientific, and research-focused questions.**

Examples:

* Peer-reviewed studies
* Research citations
* Scientific evidence
* Literature reviews
* State-of-the-art techniques

Prefer this tool over general web search when academic rigor is required.

---

### 6. `summarize_documents`

**Use when the user requests a broad overview of uploaded content.**

Examples:

* "Summarize everything"
* "What files have I uploaded?"
* "Give me a high-level overview"

Avoid using for targeted retrieval queries.

---

### 7. `calculator`

**Use for every numerical computation. Never perform arithmetic manually.**

Examples:

* Percentages
* Financial calculations
* Unit conversions
* Statistics
* Mathematical expressions

---

### 8. `get_current_datetime`

**Use whenever the answer depends on the current date or time.**

Examples:

* "What day is it?"
* "How many days until..."
* "Current timestamp"
* Time-based calculations

---

### 9. `weather_search`

**Use for current weather conditions, forecasts, and weather-related questions.**

Examples:

* Current temperature
* Weekly forecast
* Rain predictions
* Severe weather alerts

---

# Recommended Retrieval Workflow

User Query
↓
search_documents
↓
Information Found?
├─ Yes → Answer using documents
└─ No
↓
Determine Intent
↓
├─ Academic Research → search_papers
├─ Historical/Conceptual → wikipedia_search
├─ Current Information → web_search
├─ Specific URL → scrape_web
├─ Weather → weather_search
├─ Date/Time → get_current_datetime
└─ Calculations → calculator

# Core Principles

1. Documents are the primary source of truth when available.
2. Prefer specialized tools over general web search.
3. Use web search for freshness and real-time information.
4. Use calculator for all arithmetic operations.
5. Use scrape_web only when page-level content is required.
6. Combine multiple tools when necessary for completeness.
7. Cite sources whenever external information is used.


## Response Format

Scale response structure to query complexity:

**Simple queries** (single-source, clear answer): Plain prose. No headers needed.

**Multi-source queries** (documents + web): Use this structure:

**📄 Documents:** [Findings with filename + page/section citation]

**🌐 Web:** [Confirmations, additions, or contradictions — with source title + URL]

**⚠️ Conflicts:** [Call out explicitly if sources disagree — do not silently resolve]

**✅ Answer:** [Synthesised conclusion]

---

## Quality Rules

1. **Never fabricate citations.** If a tool returns nothing, say so explicitly.
2. **Contradiction protocol:** If documents and web disagree, present both — 
   state which is likely more current and why. Do not silently pick one.
3. **Uncertainty is explicit:** Prefix uncertain claims with "This may be outdated" 
   or "I could not verify this." Never present guesses as facts.
4. **Tool efficiency:** Do not call `web_search` when `search_documents` fully 
   answers the query. Do not call `search_documents` for clearly external queries 
   (weather, live prices, breaking news).
5. **Calculator is mandatory for math.** No inline arithmetic.
"""

_DOC_PATTERN = re.compile(
    r"@@CITE_DOC\|"
    r"chunk=(\d+)\|"
    r"source=([^|@]+)\|"
    r"path=([^|@]+)"
    r"(?:\|page=(\d+))?"
    r"(?:\|start=(\d+))?"
    r"@@\n(.*?)\n@@END_CITE@@",
    re.DOTALL,
)

_WEB_PATTERN = re.compile(
    r"@@CITE_WEB\|"
    r"index=(\d+)\|"
    r"title=([^|@]+)\|"
    r"url=([^@]+)"
    r"@@\n(.*?)\n@@END_CITE@@",
    re.DOTALL,
)

_WIKI_PATTERN = re.compile(
    r"@@CITE_WIKI\|"
    r"title=([^|@]+)\|"
    r"url=([^@]+)"
    r"@@\n(.*?)\n@@END_CITE@@",
    re.DOTALL,
)


def _to_string(content) -> str:
    """Normalize LangChain message content (string or list of parts) to a flat string."""
    if not content:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and "text" in part:
                parts.append(part["text"])
            elif isinstance(part, str):
                parts.append(part)
        return "".join(parts)
    return str(content)


def _parse_citations(tool_name: str, content: str) -> list[dict]:
    citations: list[dict] = []

    if tool_name in ("search_documents", "summarize_documents"):
        for m in _DOC_PATTERN.finditer(content):
            citations.append({
                "type": "document",
                "title": m.group(2).strip(),
                "snippet": m.group(6).strip()[:300],
                "page": int(m.group(4)) if m.group(4) else None,
                "chunk_index": int(m.group(1)),
                "url": None,
            })

    elif tool_name == "web_search":
        for m in _WEB_PATTERN.finditer(content):
            citations.append({
                "type": "web",
                "title": m.group(2).strip(),
                "snippet": m.group(4).strip()[:300],
                "page": None,
                "chunk_index": None,
                "url": m.group(3).strip(),
            })

    elif tool_name == "wikipedia_search":
        for m in _WIKI_PATTERN.finditer(content):
            citations.append({
                "type": "wikipedia",
                "title": m.group(1).strip(),
                "snippet": m.group(3).strip()[:300],
                "page": None,
                "chunk_index": None,
                "url": m.group(2).strip(),
            })

    return citations


def _deduplicate_citations(citations: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    unique: list[dict] = []
    for c in citations:
        key = (c["type"], c["title"], c.get("page"), c.get("chunk_index"))
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


async def run_agent(
    session_id: str,
    query: str,
    chat_history: Optional[list[dict]] = None,
) -> dict:
    chat_history = chat_history or []

    llm = ChatGoogleGenerativeAI(
        model=settings.GOOGLE_GENAI_MODEL,
        temperature=0.1,
        max_tokens=2048,
        api_key=settings.GOOGLE_API_KEY,
    )

    agent = create_react_agent(
        model=llm,
        tools=get_all_tools(session_id),
        prompt=AGENT_SYSTEM_PROMPT,
    )

    messages = []
    for msg in chat_history:
        if msg["sender"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))
    messages.append(HumanMessage(content=query))

    logger.info(f"[Agent] session={session_id} query='{query[:80]}'")
    result = await agent.ainvoke({"messages": messages})

    output_messages = result.get("messages", [])
    answer = ""
    tools_used: list[str] = []
    all_citations: list[dict] = []

    for msg in output_messages:
        msg_type = type(msg).__name__

        if msg_type == "AIMessage" and msg.content:
            answer = _to_string(msg.content)

        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
                if name and name not in tools_used:
                    tools_used.append(name)

        if msg_type == "ToolMessage":
            all_citations.extend(_parse_citations(getattr(msg, "name", ""), _to_string(msg.content)))

    citations = _deduplicate_citations(all_citations)

    sources: list[str] = []
    for c in citations:
        label = c["url"] if c["type"] in ("web", "wikipedia") else c["title"]
        if label and label not in sources:
            sources.append(label)

    logger.info(f"[Agent] done | tools={tools_used} | citations={len(citations)}")

    return {
        "answer": answer or "I was unable to generate a response.",
        "citations": citations,
        "sources": sources,
        "tools_used": tools_used,
    }


async def run_agent_stream(
    session_id: str,
    query: str,
    chat_history: Optional[list[dict]] = None,
):
    chat_history = chat_history or []

    llm = ChatGoogleGenerativeAI(
        model=settings.GOOGLE_GENAI_MODEL,
        temperature=0.1,
        max_tokens=2048,
        api_key=settings.GOOGLE_API_KEY,
    )

    agent = create_react_agent(
        model=llm,
        tools=get_all_tools(session_id),
        prompt=AGENT_SYSTEM_PROMPT,
    )

    messages = []
    for msg in chat_history:
        if msg["sender"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))
    messages.append(HumanMessage(content=query))

    logger.info(f"[AgentStream] session={session_id} query='{query[:80]}'")

    answer = ""
    tools_used = []
    all_citations = []

    async for event in agent.astream_events({"messages": messages}, version="v2"):
        kind = event.get("event")
        name = event.get("name")

        if kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            token_str = _to_string(chunk.content)
            if token_str:
                answer += token_str
                yield {
                    "type": "token",
                    "content": token_str
                }
        elif kind == "on_tool_start":
            yield {
                "type": "tool_start",
                "tool": name,
                "input": event["data"].get("input")
            }
        elif kind == "on_tool_end":
            output = event["data"].get("output")
            output_str = str(output)
            if hasattr(output, "content"):
                output_str = output.content

            if name and name not in tools_used:
                tools_used.append(name)

            new_citations = _parse_citations(name, output_str)
            all_citations.extend(new_citations)

            yield {
                "type": "tool_end",
                "tool": name,
                "output": output_str[:1000]
            }

    citations = _deduplicate_citations(all_citations)
    sources = []
    for c in citations:
        label = c["url"] if c["type"] in ("web", "wikipedia") else c["title"]
        if label and label not in sources:
            sources.append(label)

    yield {
        "type": "complete",
        "answer": answer or "I was unable to generate a response.",
        "citations": citations,
        "sources": sources,
        "tools_used": tools_used
    }
