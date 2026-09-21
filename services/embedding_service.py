"""
services/embedding_service.py - Azure OpenAI Vector Embedding Service

Generates text vector embeddings in batches using the configured
Azure AI Foundry / OpenAI embedding deployment.
"""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from openai import AzureOpenAI, APIError, AuthenticationError, RateLimitError

# Add project root directory to Python path if run standalone
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config


def normalize_azure_endpoint(endpoint: str) -> str:
    """Extracts base Azure endpoint without REST suffixes."""
    cleaned = endpoint.strip().rstrip("/")
    if "/openai" in cleaned:
        cleaned = cleaned.split("/openai")[0]
    return cleaned


class EmbeddingService:
    """Service to generate vector embeddings using Azure OpenAI model deployments."""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        api_version: Optional[str] = None,
        deployment_name: Optional[str] = None,
        expected_dimensions: Optional[int] = None,
    ):
        raw_endpoint = endpoint or config.AZURE_OPENAI_ENDPOINT
        self.endpoint = normalize_azure_endpoint(raw_endpoint)
        self.api_key = api_key or config.AZURE_OPENAI_API_KEY
        self.api_version = api_version or config.AZURE_OPENAI_API_VERSION or "2024-02-15-preview"
        self.deployment_name = deployment_name or config.AZURE_OPENAI_EMBEDDING_DEPLOYMENT
        self.expected_dimensions = expected_dimensions or config.AZURE_OPENAI_EMBEDDING_DIMENSIONS

        self.client = AzureOpenAI(
            azure_endpoint=self.endpoint,
            api_key=self.api_key,
            api_version=self.api_version,
        )

    def generate_embedding(self, text: str) -> List[float]:
        """
        Generates an embedding vector for a single string.

        :param text: Input text to embed.
        :return: List of floats representing the embedding vector.
        """
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("Cannot generate embedding for empty text.")

        response = self.client.embeddings.create(
            model=self.deployment_name,
            input=cleaned,
        )
        return response.data[0].embedding

    def generate_query_embedding(self, query: str) -> List[float]:
        """
        Helper method to generate an embedding vector for a user query during search.
        """
        return self.generate_embedding(query)

    def generate_embeddings_batch(
        self,
        texts: List[str],
        batch_size: int = 16,
    ) -> List[List[float]]:
        """
        Generates embeddings for a list of strings in batches to maximize throughput
        and stay within Azure request payload limits.

        :param texts: List of text strings to embed.
        :param batch_size: Number of text inputs per API request.
        :return: List of embedding vectors in the exact order of input texts.
        """
        if not texts:
            return []

        all_embeddings: List[List[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            # Replace empty strings with a single space to avoid API errors
            sanitized_batch = [t if t.strip() else " " for t in batch]

            response = self.client.embeddings.create(
                model=self.deployment_name,
                input=sanitized_batch,
            )

            # Ensure vectors are ordered correctly by response index
            sorted_data = sorted(response.data, key=lambda item: item.index)
            for item in sorted_data:
                all_embeddings.append(item.embedding)

        return all_embeddings

    def embed_chunks(
        self,
        chunks: List[Dict[str, Any]],
        batch_size: int = 16,
    ) -> List[Dict[str, Any]]:
        """
        Embeds a list of document chunk dictionaries in batches, attaching
        the 'content_vector' field to each chunk dict.

        :param chunks: List of chunk dictionaries containing a 'content' key.
        :param batch_size: Batch size for API requests.
        :return: The same list of chunks with 'content_vector' added.
        """
        if not chunks:
            return []

        texts = [chunk["content"] for chunk in chunks]
        vectors = self.generate_embeddings_batch(texts, batch_size=batch_size)

        for chunk, vector in zip(chunks, vectors):
            chunk["content_vector"] = vector

        return chunks


if __name__ == "__main__":
    print("=" * 65)
    print(" Embedding Service - Self Test")
    print("=" * 65)

    try:
        service = EmbeddingService()
        sample_texts = [
            "Acme Corp standard working hours are 40 hours per week.",
            "Employees receive 25 days of paid annual vacation leave.",
        ]

        print(f"Deployment: {service.deployment_name}")
        print(f"Batch Size: {len(sample_texts)} texts")
        print("Generating batch embeddings...")

        vectors = service.generate_embeddings_batch(sample_texts)
        print(f"[SUCCESS] Generated {len(vectors)} vectors.")
        print(f"  Vector 1 dimensions: {len(vectors[0])}")
        print(f"  Vector 2 dimensions: {len(vectors[1])}")

    except Exception as e:
        print(f"[ERROR] Embedding test failed: {e}")

    print("\n" + "=" * 65)
    print(" Self Test Finished.")
    print("=" * 65)
