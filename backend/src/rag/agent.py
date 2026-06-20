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

## When to Use Each Tool

- `search_documents` — Any query that may relate to uploaded files. Always try first.
- `web_search` — When documents are absent, stale, or incomplete. Also for current events, prices, recent research.
- `wikipedia_search` — Definitions, historical background, encyclopedic context.
- `search_papers` — Academic citations, peer-reviewed research, scientific claims.
- `calculator` — All numeric computation, no exceptions. Never mental-math a number.
- `get_current_datetime` — Any time/date reference.
- `weather_search` — Current weather queries.
- `summarize_documents` — "Summarize everything", "what did I upload?", broad overviews.

---

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
