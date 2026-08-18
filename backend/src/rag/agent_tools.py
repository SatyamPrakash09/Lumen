import ast
import logging
import math
import operator
import os
from datetime import datetime, UTC
import httpx
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

from src.config.settings import get_settings

settings = get_settings()


def make_rag_search_tool(session_id: str):
    from src.rag.vector_store import similarity_search

    @tool
    def search_documents(query: str) -> str:
        """
            Search the uploaded documents associated with the current chat session.

            Use this tool whenever the user's question may be answered using uploaded
            files (PDF, DOCX, TXT, Markdown, CSV, etc.).

            This should ALWAYS be the first retrieval tool used before searching the web.

            Examples:
            - "Summarize the uploaded report."
            - "What does page 12 mention?"
            - "Find all mentions of transformer architecture."
            - "What is the refund policy in my PDF?"

            Do NOT use this tool for:
            - Current events
            - General knowledge
            - Information outside uploaded documents

            Args:
                query: Natural language search query.

            Returns:
                Relevant document chunks with citation metadata that can be referenced
                in the final answer.
        """
        try:
            docs = similarity_search(session_id, query)
            if not docs:
                return "NO_DOCS: No relevant content found in the uploaded documents."

            parts = []
            for i, doc in enumerate(docs, 1):
                meta = doc.metadata
                source = meta.get("source", "Unknown")
                page = meta.get("page", None)
                start = meta.get("start_index", None)
                filename = os.path.basename(source)

                page_part = f"|page={page}" if page is not None else ""
                start_part = f"|start={start}" if start is not None else ""
                header = f"@@CITE_DOC|chunk={i}|source={filename}|path={source}{page_part}{start_part}@@"
                parts.append(f"{header}\n{doc.page_content[:600]}\n@@END_CITE@@")

            return "\n\n".join(parts)
        except Exception as e:
            logger.error(f"[Tool:search_documents] Error: {e}")
            return f"Error searching documents: {str(e)}"

    return search_documents


@tool
async def web_search(query: str, max_results: int = 5) -> str:
    """
    Search the public web using Google Search.

    Use this tool only when:

    - uploaded documents do not contain the answer
    - information must be verified
    - current or recent information is required
    - additional context is needed

    Prefer search_documents whenever uploaded files may contain the answer.

    Examples:
    - latest Python release
    - current stock price
    - recent AI news
    - verify a fact from a PDF

    Args:
        query: Search query.
        max_results: Maximum number of search results.

    Returns:
        Web search snippets with source URLs.
    """
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://serpapi.com/search.json",
                params={
                    "api_key": settings.SERP_API_KEY,
                    "engine": "google",
                    "q": query,
                    "num": max_results,
                },
            )
            resp.raise_for_status()
            google_raw = resp.json()

        results = google_raw.get("organic_results", [])[:max_results]

        if not results:
            return "No web search results found."

        parts = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "No title").replace("|", "-")[:120].replace("\n", " ")
            url = r.get("link", "")
            snippet = r.get("snippet", "")
            header = f"@@CITE_WEB|index={i}|title={title}|url={url}@@"
            parts.append(f"{header}\n{snippet[:500]}\n@@END_CITE@@")

        return "\n\n".join(parts)
    except Exception as e:
        logger.error(f"[Tool:web_search] Error: {e}")
        return f"Web search failed: {str(e)}"


_SAFE_NODES = {
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Num, ast.Constant,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod,
    ast.Pow, ast.USub, ast.UAdd, ast.Call, ast.Name, ast.Load,
}

_SAFE_NAMES = {
    "abs": abs, "round": round,
    "sqrt": math.sqrt, "log": math.log, "log10": math.log10,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "pi": math.pi, "e": math.e,
    "ceil": math.ceil, "floor": math.floor,
    "factorial": math.factorial, "pow": pow,
}

_SAFE_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def _safe_eval(node):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    elif isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant: {node.value}")
    elif isinstance(node, ast.BinOp):
        op = _SAFE_OPS.get(type(node.op))
        if not op:
            raise ValueError("Unsupported operator")
        return op(_safe_eval(node.left), _safe_eval(node.right))
    elif isinstance(node, ast.UnaryOp):
        op = _SAFE_OPS.get(type(node.op))
        if not op:
            raise ValueError("Unsupported unary operator")
        return op(_safe_eval(node.operand))
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Function calls must be named.")
        fn = _SAFE_NAMES.get(node.func.id)
        if not fn:
            raise ValueError(f"Unsupported function: {node.func.id}")
        return fn(*[_safe_eval(a) for a in node.args])
    elif isinstance(node, ast.Name):
        val = _SAFE_NAMES.get(node.id)
        if val is None:
            raise ValueError(f"Unsupported variable: {node.id}")
        return val
    raise ValueError(f"Unsupported node: {type(node)}")


@tool
def calculator(expression: str) -> str:
    """
    Safely evaluate mathematical expressions.

    Supports:

    - +, -, *, /, //, %, **
    - sqrt
    - factorial
    - sin, cos, tan
    - log, log10
    - ceil, floor
    - constants pi and e

    Always use this tool whenever a calculation is required instead of estimating.

    Examples:
    - 2+2
    - sqrt(49)
    - factorial(10)
    - sin(pi/4)

    Args:
        expression: Mathematical expression.

    Returns:
        Computed result or an error message.
    """
    try:
        expr = expression.strip()
        tree = ast.parse(expr, mode="eval")
        for node in ast.walk(tree):
            if type(node) not in _SAFE_NODES:
                raise ValueError(f"Unsafe element: {type(node).__name__}")
        result = _safe_eval(tree)
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return f"{expression} = {result}"
    except ZeroDivisionError:
        return "Error: Division by zero."
    except Exception as e:
        return f"Error: {str(e)}"


@tool
def get_current_datetime(timezone: str = "UTC") -> str:
    """
    Return the current date and time.

    Useful for answering questions involving:

    - today's date
    - current UTC time
    - timestamps
    - scheduling context
    - date calculations

    Args:
        timezone: Reserved for future support. Currently ignored.

    Returns:
        Current UTC date and time in multiple formats.
    """
    now = datetime.now(UTC)
    return (
        f"Current date and time (UTC):\n"
        f"  Date: {now.strftime('%A, %B %d, %Y')}\n"
        f"  Time: {now.strftime('%H:%M:%S')} UTC\n"
        f"  ISO:  {now.isoformat()}"
    )


def make_summarize_tool(session_id: str):
    from src.rag.vector_store import get_or_create_collection

    @tool
    def summarize_documents(focus: str = "") -> str:
        """
    Generate a high-level summary of the uploaded documents.

    Use this tool when the user requests:

    - an overview
    - executive summary
    - key points
    - document synopsis
    - main ideas

    Optionally provide a focus topic to bias the summary.

    Examples:
    - "Summarize the document."
    - "Give me the key findings."
    - "Summarize only the security section."

    Args:
        focus: Optional topic to prioritize.

    Returns:
        Representative document excerpts with citation metadata.
    """
        try:
            store = get_or_create_collection(session_id)
            query = focus if focus else "main topic summary overview introduction"
            results = store.similarity_search(query, k=8)

            if not results:
                return "No documents found in this session."

            parts = []
            for i, doc in enumerate(results, 1):
                meta = doc.metadata
                source = meta.get("source", "Unknown")
                page = meta.get("page", None)
                filename = os.path.basename(source)
                page_part = f"|page={page}" if page is not None else ""
                header = f"@@CITE_DOC|chunk={i}|source={filename}|path={source}{page_part}@@"
                parts.append(f"{header}\n{doc.page_content[:400]}\n@@END_CITE@@")

            return "\n\n".join(parts)
        except Exception as e:
            logger.error(f"[Tool:summarize_documents] Error: {e}")
            return f"Error summarising documents: {str(e)}"

    return summarize_documents


@tool
async def search_hacker_news(
    query: str,
    tags: str = "story",
    numeric_filters: str = "",
):
    """
    Search Hacker News stories and comments.

    Useful for finding:

    - startup discussions
    - engineering news
    - programming trends
    - AI community discussions
    - launch announcements

    Supports searching stories, comments, or the front page.

    Args:
        query: Search keywords.
        tags: One of "story", "comment", or "front_page".
        numeric_filters: Optional Algolia numeric filters.

    Returns:
        Matching Hacker News posts with metadata.
    """

    url = "https://hn.algolia.com/api/v1/search"

    params = {
        "query": query,
        "tags": tags,
    }

    if numeric_filters:
        params["numericFilters"] = numeric_filters

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()

        data = response.json()
        hits = data.get("hits", [])

        if not hits:
            return "No Hacker News results found."

        parts = []
        for hit in hits:
            title = (hit.get("title") or "Untitled").replace("|", "-")[:120]
            hn_url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
            body = hit.get("story_text") or hit.get("comment_text") or ""
            header = f"@@CITE_HACKERNEWS|title={title}|url={hn_url}@@"
            parts.append(f"{header}\n{body[:500]}\n@@END_CITE@@")

        return "\n\n".join(parts)

    except httpx.HTTPStatusError as e:
        return {"error": f"Request failed: {str(e)}"}

    except Exception as e:
        return {"error": f"Hacker News search failed: {str(e)}"}


def get_all_tools(session_id: str) -> list:
    return [
        make_rag_search_tool(session_id),
        web_search,
        calculator,
        get_current_datetime,
        make_summarize_tool(session_id),
        search_hacker_news,
    ]
