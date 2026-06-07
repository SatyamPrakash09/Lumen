from functools import lru_cache
from langchain_huggingface import HuggingFaceEmbeddings
from src.config.settings import get_settings

settings = get_settings()


@lru_cache(maxsize=4)
def _get_embedding_model(model_name: str) -> HuggingFaceEmbeddings:
    """Cache the embedding model so it is only loaded once per process."""
    return HuggingFaceEmbeddings(model_name=model_name)


class Embeddings:
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or settings.EMBEDDING_MODEL
        self.model = _get_embedding_model(self.model_name)

    async def create_document_embeddings(self, documents: list[str]) -> list[list[float]]:
        """Embed a list of text strings (document chunks)."""
        try:
            embeddings = self.model.embed_documents(documents)
            return embeddings
        except Exception as e:
            raise Exception(f"Error creating document embeddings: {str(e)}")

    async def create_query_embedding(self, query: str) -> list[float]:
        """Embed a single query string."""
        try:
            embedding = self.model.embed_query(query)
            return embedding
        except Exception as e:
            raise Exception(f"Error creating query embedding: {str(e)}")
