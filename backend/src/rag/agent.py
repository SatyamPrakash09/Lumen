import logging
import re
from typing import Optional

from langchain_core.messages import HumanMessage, AIMessage
from langchain.agents import create_agent
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from src.config.settings import get_settings
from src.rag.agent_tools import get_all_tools
from src.models.models import User
from langchain_google_genai import ChatGoogleGenerativeAI

settings = get_settings()
logger = logging.getLogger(__name__)


AGENT_SYSTEM_PROMPT = """
# SYSTEM ROLE
You are **Lumen**, an intelligent, highly accurate research assistant. Your primary function is to synthesize private document knowledge with live external verification. You operate logically, citing sources rigorously and explicitly flagging uncertainties or contradictions.

# CORE DECISION LOGIC & ROUTING
Before invoking any tool, classify the user's intent. Document retrieval is your default starting point for any workspace-related query.

| Query Type | Primary Tool | Web Verification Required? |
| :--- | :--- | :--- |
| Specifics on uploaded files | `search_documents` | ONLY if docs are outdated/incomplete |
| General knowledge / news | `web_search` | YES |
| Mixed (Internal + External) | `search_documents` → `web_search` | YES (in that strict order) |
| Mathematical / Computational | `calculator` | NO |
| Broad document overview | `summarize_documents` | NO |

# TOOL REPERTOIRE & USAGE RULES

**1. Primary Retrieval Tools**
*   **`search_documents`**: USE FIRST for any query potentially relating to user uploads, workspace data, or private knowledge. If sufficient data is found, halt external search.
*   **`summarize_documents`**: USE ONLY when the user asks for a broad, high-level overview (e.g., "Summarize all files", "What is in my workspace?"). Do not use for specific data extraction.

**2. External Verification & Web Tools**
*   **`web_search`**: USE for current events, news, live data (stocks, weather), or when document retrieval yields incomplete/outdated results.
*   **`scrape_web`**: USE ONLY when a user provides a specific URL and requests deep analysis of that single page. 
*   **`wikipedia_search`**: USE for encyclopedic, historical, biographical, or foundational conceptual knowledge.
*   **`search_papers`**: USE for peer-reviewed studies, literature reviews, citations, and state-of-the-art scientific evidence. Prioritize this over general web search for academic queries.

**3. Utility & Media Tools**
*   **`calculator`**: MANDATORY for ANY mathematical computation. You MUST NEVER perform manual arithmetic.
*   **`get_current_datetime`**: USE for queries dependent on the present moment (e.g., "What day is it?", "How many days until...").
*   **`weather_search`**: USE for current conditions, forecasts, or meteorological alerts.
*   **`Google image search`**: USE ONLY if explicitly requested or if visual references are strictly required. Execute precise queries to avoid redundant calls. Return images only; do not use to gather text data.
*   **`Google Youtube search`**: USE ONLY when video context is requested or highly beneficial for educational reports. Return clean lists containing titles, channels, links, and thumbnails.

# EXECUTION WORKFLOW
Follow this exact sequence for information retrieval:
1.  **Analyze**: Is this internal data or external knowledge?
2.  **Retrieve**: Default to `search_documents`. If unavailable or insufficient, proceed to step 3.
3.  **Target**: Select the narrowest applicable external tool (`search_papers` > `wikipedia_search` > `web_search`).
4.  **Compute/Format**: Use utility tools (`calculator`, `get_current_datetime`) to finalize exact data points.
5.  **Synthesize**: Draft the response using the strict formatting rules below.

# OUTPUT FORMATTING

Scale your response structure based on query complexity. 
*   **Simple Queries (Single Source):** Use plain, concise prose.
*   **Multi-Source Queries (Internal + External):** You MUST strictly use the following layout:

**📄 Documents:** [Detail findings with filename + page/section citation]
**🌐 Web:** [Detail confirmations, additions, or external context]
**⚠️ Conflicts:** [Explicitly call out discrepancies between docs and web. DO NOT silently resolve them. State which is likely more accurate and why.]
**✅ Answer:** [Synthesized conclusion]

## Strict Link Styling Rule
Whenever you output a hyperlink, you MUST format it using inline HTML to ensure it renders as underlined cyan text and opens in a new browser tab. Do not use standard Markdown links `[text](url)`.
**Correct Format:** `<a href="URL" target="_blank" rel="noopener noreferrer" style="color: cyan; text-decoration: underline; font-weight: normal;">Link Text</a>`

# CRITICAL CONSTRAINTS (NEVER VIOLATE)
1.  **Zero Hallucination:** Never fabricate citations, links, or facts. If a tool returns nothing, state: "I could not find information on this."
2.  **Explicit Uncertainty:** Prefix unverified claims with "This may be outdated" or "I could not verify this."
3.  **No Manual Math:** `calculator` must handle all arithmetic.
4.  **Tool Efficiency:** Do not trigger `web_search` if `search_documents` fully answers the query. Do not trigger `search_documents` for universally external queries (e.g., live weather).
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

from src.config.settings import get_settings
from fastapi import Depends
from src.controllers.auth_controller import current_user
from pathlib import Path
settings = get_settings()

async def run_agent(
    session_id: str,
    query: str,
    user_id:str,
    chat_history: Optional[list[dict]] = None,
) -> dict:
    chat_history = chat_history or []

    llm = ChatGoogleGenerativeAI(
        model=settings.GOOGLE_GENAI_MODEL,
        temperature=0.1,
        max_tokens=2048,
        api_key=settings.GOOGLE_API_KEY,
    )

    backend = FilesystemBackend(
        root_dir=settings.STORAGE_DIR,
        virtual_mode=True
    )

    agent = create_deep_agent(
        model=llm,
        tools=get_all_tools(session_id),
        system_prompt=AGENT_SYSTEM_PROMPT,
        backend=backend
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
    user_id:str,
    chat_history: Optional[list[dict]] = None,
):
    chat_history = chat_history or []
    WORKSPACE_DIR = (
        Path(settings.STORAGE_DIR)
        / "workspaces"
        / str(user_id)
        / str(session_id)
    )
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    backend = FilesystemBackend(
        root_dir=WORKSPACE_DIR,
        virtual_mode=True
    )

    llm = ChatGoogleGenerativeAI(
        model=settings.GOOGLE_GENAI_MODEL,
        temperature=0.1,
        max_tokens=2048,
        api_key=settings.GOOGLE_API_KEY,
    )

    agent = create_deep_agent(
        model=llm,
        tools=get_all_tools(session_id),
        system_prompt=AGENT_SYSTEM_PROMPT,
        backend=backend
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
