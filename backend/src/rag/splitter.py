from langchain_text_splitters import RecursiveCharacterTextSplitter


def split_document(documents, chunk_size: int = 1000, chunk_overlap: int = 200):
    """Split a list of LangChain Document objects into smaller chunks."""
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        add_start_index=True,
    )
    chunks = text_splitter.split_documents(documents)
    return chunks
