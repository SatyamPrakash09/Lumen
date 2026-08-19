import ast
import logging
import math
import operator
import os
from datetime import datetime, UTC
import requests
import serpapi
import wikipediaapi
from ddgs import DDGS
from langchain_core.tools import tool
from bs4 import BeautifulSoup

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
def web_search(query: str, max_results: int = 5) -> str:
    """
    Search the public web using DuckDuckGo and Google Search.

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
        with DDGS() as ddgs:
            ddgs_results = list(ddgs.text(query, max_results=max_results))

        serpapi_client = serpapi.Client(api_key= settings.SERP_API_KEY)
        google_raw = serpapi_client.search({
            "engine": "google",
            "q": f"{query}"
        })
        # Normalize Google organic results to match DuckDuckGo format
        for gr in google_raw.get("organic_results", []):
            ddgs_results.append({
                "title": gr.get("title", "No title"),
                "href": gr.get("link", ""),
                "body": gr.get("snippet", ""),
            })

        if not ddgs_results:
            return "No web search results found."

        parts = []
        for i, r in enumerate(ddgs_results, 1):
            title = r.get("title", "No title").replace("|", "-")[:120].replace("\n", " ")
            url = r.get("href", "")
            header = f"@@CITE_WEB|index={i}|title={title}|url={url}@@"
            parts.append(f"{header}\n{r.get('body', '')[:500]}\n@@END_CITE@@")

        return "\n\n".join(parts)
    except Exception as e:
        logger.error(f"[Tool:web_search] Error: {e}")
        return f"Web search failed: {str(e)}"

@tool
def search_images(query:str) -> list[dict]:
    """
    Search Google Images for high-quality visual references.

    This tool should be used only when visual assets are required for a report,
    documentation, presentation, or user request. It is intended to locate
    relevant images such as logos, diagrams, architecture illustrations,
    timelines, screenshots, and photographs.

    Input:
        query: A specific search query (e.g., "Hugging Face logo",
        "MITRE ATT&CK matrix", "Kubernetes architecture").

    Returns:
        Up to 12 image search results, each including:
        - number: Search result position.
        - image_title: Image title or description.

    Guidelines:
        - Use one focused query instead of multiple broad searches.
        - Do not use for factual information or text research.
        - Avoid repeating searches for the same topic unless the previous
          results were insufficient.
    """
    serpapi_client = serpapi.Client(api_key= settings.SERP_API_KEY)
    google_image_results = serpapi_client.search({
        "engine": "google_images",
        "q": f"{query}"
    })
    results=google_image_results.as_dict()["images_results"][:12]
    image_details=[{
        "number": image["position"],
        "image_title": image["title"],
        "image_link" : image["original"]
    } for image in results]
    return image_details
    

@tool
def wikipedia_search(topic: str, sentences: int = 5) -> str:
    """
    Retrieve encyclopedic information from Wikipedia.

    Use this tool for:

    - definitions
    - historical background
    - biographies
    - scientific concepts
    - general knowledge

    Avoid using it for:
    - current news
    - rapidly changing information
    - product pricing

    Args:
        topic: Wikipedia article title or topic.
        sentences: Number of summary sentences.

    Returns:
        Concise Wikipedia summary with citation.
    """
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

# semantic scholar tool
@tool
def search_papers(query: str) -> str:
    """
    Search Semantic Scholar for academic research papers.

    Use this tool for:

    - peer-reviewed research
    - scientific evidence
    - citations
    - literature review
    - state-of-the-art methods

    Prefer this over web search whenever the user explicitly asks for research papers.

    Examples:
    - RAG papers
    - Vision Transformer research
    - diffusion models
    - reinforcement learning survey

    Args:
        query: Research topic.

    Returns:
        Up to five relevant papers including title, authors, year,
        abstract, and Semantic Scholar URL.
    """
    
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
    """
    Retrieve the current weather conditions for a city.

    Use when the user asks about:

    - weather
    - temperature
    - humidity
    - current conditions

    Do not use for weather forecasts.

    Args:
        city: City or location name.

    Returns:
        Current weather information including temperature,
        humidity, and conditions.
    """
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
        response = requests.get(url, params=params, timeout=10)
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

    except requests.RequestException as e:
        return {"error": f"Request failed: {str(e)}"}

    except ValueError:
        return {"error": "Invalid JSON response from Hacker News API"}


@tool
def scrape_web(url: str) -> str:
    """
    Download and extract readable text from a webpage.

    Use this tool after obtaining a URL from the user or another tool.

    The scraper removes scripts, navigation, styles, and other boilerplate,
    returning the primary textual content.

    Examples:
    - summarize an article
    - extract documentation
    - analyze a blog post

    Do not use this tool to search the internet.
    Use web_search first when no URL is available.

    Args:
        url: Fully qualified webpage URL.

    Returns:
        Cleaned text extracted from the webpage.
    """

    try:
        response = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"}
        )

        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()

        text = soup.get_text(separator="\n")

        return text[:15000]

    except Exception as e:
        return str(e)

@tool
def search_youtube(query:str) -> list[dict] :
        """
        Search YouTube for relevant videos matching a given topic or query.

        Use this tool when the user requests YouTube videos, tutorials, lectures, demonstrations, interviews, conference talks, documentaries, product announcements, or any other video-based learning resources. It is also useful when creating research reports, documentation, presentations, or educational content that would benefit from video references.

        Input:
            query: A concise and specific search query describing the desired videos.

        Returns:
            An organized list of up to 12 relevant YouTube videos. Each result includes:
            - number: Position of the video in the search results.
            - video_title: Title of the video.
            - channel_name: Name of the YouTube channel.
            - video_link: Direct link to the YouTube video.
            - thumbnail: Thumbnail image representing the video.

        Presentation Guidelines:
        - Display the results in a clean, well-organized, and numbered format.
        - Use the provided thumbnail as the visual preview for each video whenever the output format supports images.
        - When HTML output is supported, render the results as a professional, responsive layout (such as cards or a table) with proper alignment and spacing.
        - Ensure each thumbnail is aligned with its corresponding title, channel name, and video link.
        - Make the video title clickable using the video URL.
        - Preserve the original search ranking and avoid reordering the results.
        - Ensure the HTML is valid, semantic, visually consistent, and free of broken layouts or overlapping elements.

        Usage Guidelines:
        - Use specific search queries (e.g., "Hugging Face Security Incident July 2026", "LangGraph tutorial", "MITRE ATT&CK explained") instead of broad topics.
        - Perform only one search per unique topic unless additional videos are explicitly required.
        - Do not use this tool for factual research when reliable textual sources are more appropriate. Use it only when video references are requested or would significantly improve the response.
        """
        serpapi_client = serpapi.Client(api_key= settings.SERP_API_KEY)
        google_image_results = serpapi_client.search({
            "engine": "youtube",
            "search_query": f"{query}"
        })
        results=google_image_results.as_dict()["video_results"][:12]
        video_details=[{
            "number": video["position_on_page"],
            "video_title": video["title"],
            "video_link" : video["link"],
            "channel_name": video["channel"]["name"],
            "thumbnail": video["thumbnail"]["static"]
        } for video in results]
        return video_details
    
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
        scrape_web,
        search_images,
        search_youtube,
    ]
