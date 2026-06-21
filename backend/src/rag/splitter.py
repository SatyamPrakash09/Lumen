from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.config.settings import get_settings


def split_document(documents, chunk_size: int | None = None, chunk_overlap: int | None = None):
    """Split a list of LangChain Document objects into smaller chunks."""
    settings = get_settings()
    chunk_size = chunk_size or settings.CHUNK_SIZE
    chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        add_start_index=True,
    )
    chunks = text_splitter.split_documents(documents)
    return chunks
