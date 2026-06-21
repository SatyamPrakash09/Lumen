import ast
import logging
import math
import operator
import os
from datetime import datetime, UTC
import requests

import wikipediaapi
from ddgs import DDGS
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

from src.config.settings import get_settings

settings = get_settings()


def make_rag_search_tool(session_id: str):
    from src.rag.vector_store import similarity_search

    @tool
    def search_documents(query: str) -> str:
        """
        Search uploaded documents for content relevant to the query.
        Always call this tool first before any other tool.
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
def web_search(query: str, max_results: int = 5) -> str:
    """
    Search the web via DuckDuckGo to verify and enrich document findings.
    Always call this after search_documents.
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))

        if not results:
            return "No web search results found."

        parts = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "No title").replace("|", "-")[:120].replace("\n", " ")
            url = r.get("href", "")
            header = f"@@CITE_WEB|index={i}|title={title}|url={url}@@"
            parts.append(f"{header}\n{r.get('body', '')[:500]}\n@@END_CITE@@")

        return "\n\n".join(parts)
    except Exception as e:
        logger.error(f"[Tool:web_search] Error: {e}")
        return f"Web search failed: {str(e)}"


@tool
def wikipedia_search(topic: str, sentences: int = 5) -> str:
    """Search Wikipedia for encyclopedic background, definitions, or history."""
    try:
        wiki = wikipediaapi.Wikipedia(
            user_agent="Lumen-AI-Agent/1.0 (contact@lumen.app)",
            language="en",
        )
        page = wiki.page(topic)

        if not page.exists():
            return f"No Wikipedia article found for '{topic}'."

        summary = ". ".join(page.summary.split(". ")[:sentences])
        if not summary.endswith("."):
            summary += "."

        safe_title = page.title.replace("|", "-")
        return f"@@CITE_WIKI|title={safe_title}|url={page.fullurl}@@\n{summary}\n@@END_CITE@@"
    except Exception as e:
        logger.error(f"[Tool:wikipedia_search] Error: {e}")
        return f"Wikipedia search failed: {str(e)}"


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
    Safely evaluate a math expression.
    Supports: +, -, *, /, **, sqrt, sin, cos, tan, log, log10, factorial, ceil, floor, pi, e.
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
    """Return the current UTC date and time."""
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
        """Return a broad overview of all documents uploaded to this session."""
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

# semantic scholar tool
@tool
def search_papers(query: str) -> str:
    """Search Semantic Scholar for research papers related to a topic."""
    
    print("\nCalling search_papers tool")
    print(f"Searching papers for: {query}\n")

    url = "https://api.semanticscholar.org/graph/v1/paper/search"

    params = {
        "query": query,
        "limit": 5,
        "fields": "title,authors,year,abstract,url"
    }

    response = requests.get(url, params=params)
    data = response.json()

    papers = data.get("data", [])

    results = []

    for paper in papers:
        authors = ", ".join([a["name"] for a in paper.get("authors", [])])

        results.append(
            f"Title: {paper.get('title','')}\n"
            f"Authors: {authors}\n"
            f"Year: {paper.get('year','')}\n"
            f"Abstract: {paper.get('abstract','')}\n"
            f"URL: {paper.get('url','')}\n"
        )

    return "\n\n".join(results)

@tool
def weather_search(city: str) -> str:
    """Get current weather for a city."""

    print("\nCalling weather_search tool")

    api_key = settings.WEATHER_API

    url = f"https://api.weatherapi.com/v1/current.json?q={city}&key={api_key}"

    response = requests.get(url)

    if response.status_code != 200:
        return f"Weather API error: {response.status_code}"

    data = response.json()

    # check if API returned an error
    if "weather" not in data:
        return f"Weather data not available. API response: {data}"

    weather = data["weather"][0]["description"]
    temp = data["main"]["temp"]
    humidity = data["main"]["humidity"]

    return f"""
City: {city}
Temperature: {temp} °C
Weather: {weather}
Humidity: {humidity} %
"""

@tool
def search_hacker_news(
    query: str,
    tags: str = "story",
    numeric_filters: str = "",
):
    """
    Search Hacker News stories, comments, or front-page items.

    tags:
      - story
      - comment
      - front_page
    """

    url = "https://hn.algolia.com/api/v1/search"

    params = {
        "query": query,
        "tags": tags,
    }

    if numeric_filters:
        params["numericFilters"] = numeric_filters

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()

        return data.get("hits", [])

    except requests.RequestException as e:
        return {"error": f"Request failed: {str(e)}"}

    except ValueError:
        return {"error": "Invalid JSON response from Hacker News API"}

def get_all_tools(session_id: str) -> list:
    return [
        make_rag_search_tool(session_id),
        web_search,
        wikipedia_search,
        calculator,
        get_current_datetime,
        make_summarize_tool(session_id),
        search_papers,
        weather_search,
        search_hacker_news,

    ]
