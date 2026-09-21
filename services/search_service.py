"""
services/search_service.py - Azure AI Search Management and Hybrid Query Service

Handles:
1. Azure AI Search index lifecycle (creation, schema validation, updating).
2. Chunk uploading with idempotent primary keys.
3. Hybrid search combining BM25 keyword search + dense vector retrieval (HNSW)
   via Reciprocal Rank Fusion (RRF) with graceful fallbacks.
"""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import ResourceNotFoundError, HttpResponseError
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    VectorSearch,
    VectorSearchProfile,
    HnswAlgorithmConfiguration,
)
from azure.search.documents.models import VectorizedQuery

# Add project root directory to Python path if run standalone
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from services.embedding_service import EmbeddingService


class SearchService:
    """Service to interact with Azure AI Search indexes and execute hybrid retrieval."""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        index_name: Optional[str] = None,
        embedding_dimensions: Optional[int] = None,
    ):
        self.endpoint = endpoint or config.AZURE_SEARCH_ENDPOINT
        self.api_key = api_key or config.AZURE_SEARCH_API_KEY
        self.index_name = index_name or config.AZURE_SEARCH_INDEX_NAME
        self.embedding_dimensions = (
            embedding_dimensions or config.AZURE_OPENAI_EMBEDDING_DIMENSIONS
        )

        if not self.endpoint:
            raise ValueError("AZURE_SEARCH_ENDPOINT is missing from configuration.")
        if not self.api_key:
            raise ValueError("AZURE_SEARCH_API_KEY is missing from configuration.")
        if not self.index_name:
            raise ValueError("AZURE_SEARCH_INDEX_NAME is missing from configuration.")

        self.credential = AzureKeyCredential(self.api_key)
        self.index_client = SearchIndexClient(
            endpoint=self.endpoint, credential=self.credential
        )
        self.search_client = SearchClient(
            endpoint=self.endpoint,
            index_name=self.index_name,
            credential=self.credential,
        )
        self._embedding_service: Optional[EmbeddingService] = None

    @property
    def embedding_service(self) -> EmbeddingService:
        """Lazy-loaded EmbeddingService singleton."""
        if self._embedding_service is None:
            self._embedding_service = EmbeddingService()
        return self._embedding_service

    def index_exists(self) -> bool:
        """Checks if the configured search index already exists."""
        try:
            self.index_client.get_index(self.index_name)
            return True
        except ResourceNotFoundError:
            return False
        except HttpResponseError as e:
            if e.status_code == 404:
                return False
            raise

    def create_or_update_index(self) -> SearchIndex:
        """
        Creates or updates the Azure AI Search index matching the schema from PROJECT_CONTEXT.md:
        - id: String (Key, filterable, sortable)
        - document_name: String (Searchable, filterable, sortable, facetable)
        - chunk_id: String (Filterable)
        - page_number: Int32 (Filterable, sortable, facetable)
        - content: String (Searchable)
        - source: String (Filterable)
        - content_vector: Collection(Single) with HNSW Vector profile and dimensions from config
        """
        algorithm_config_name = "hnsw-algorithm"
        vector_profile_name = "vector-profile"

        vector_search = VectorSearch(
            algorithms=[
                HnswAlgorithmConfiguration(
                    name=algorithm_config_name,
                )
            ],
            profiles=[
                VectorSearchProfile(
                    name=vector_profile_name,
                    algorithm_configuration_name=algorithm_config_name,
                )
            ],
        )

        fields = [
            SimpleField(
                name="id",
                type=SearchFieldDataType.String,
                key=True,
                filterable=True,
                sortable=True,
            ),
            SearchableField(
                name="document_name",
                type=SearchFieldDataType.String,
                filterable=True,
                sortable=True,
                facetable=True,
            ),
            SimpleField(
                name="chunk_id",
                type=SearchFieldDataType.String,
                filterable=True,
            ),
            SimpleField(
                name="page_number",
                type=SearchFieldDataType.Int32,
                filterable=True,
                sortable=True,
                facetable=True,
            ),
            SearchableField(
                name="content",
                type=SearchFieldDataType.String,
            ),
            SimpleField(
                name="source",
                type=SearchFieldDataType.String,
                filterable=True,
            ),
            SearchField(
                name="content_vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=self.embedding_dimensions,
                vector_search_profile_name=vector_profile_name,
            ),
        ]

        index = SearchIndex(
            name=self.index_name,
            fields=fields,
            vector_search=vector_search,
        )

        return self.index_client.create_or_update_index(index)

    def upload_chunks(
        self,
        chunks: List[Dict[str, Any]],
        batch_size: int = 100,
    ) -> int:
        """
        Uploads or merges document chunks into the search index.
        Uses deterministic chunk IDs so repeated uploads overwrite rather than duplicate.

        :param chunks: List of chunk dictionaries containing fields matching the schema.
        :param batch_size: Number of documents to batch per upload request.
        :return: Total number of successfully uploaded chunks.
        """
        if not chunks:
            return 0

        total_uploaded = 0
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            results = self.search_client.merge_or_upload_documents(documents=batch)
            successful_batch = sum(1 for r in results if r.succeeded)
            total_uploaded += successful_batch

        return total_uploaded

    def get_document_count(self) -> int:
        """Returns the total number of documents indexed in the search index."""
        try:
            return self.search_client.get_document_count()
        except Exception:
            return 0

    def search(
        self,
        query: str,
        top_k: int = 4,
        vector: Optional[List[float]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Performs Hybrid Search (BM25 Keyword Search + HNSW Dense Vector Retrieval)
        combined using Reciprocal Rank Fusion (RRF).

        :param query: Natural language user question or search phrase.
        :param top_k: Number of most relevant document chunks to return (default: 4).
        :param vector: Optional pre-computed embedding vector for the query.
        :return: List of top chunk dicts with keys: document_name, chunk_id, page_number, content, score.
        """
        cleaned_query = query.strip()
        if not cleaned_query:
            return []

        # Generate query vector if not provided
        query_vector = vector
        if query_vector is None:
            query_vector = self.embedding_service.generate_query_embedding(cleaned_query)

        vector_query = VectorizedQuery(
            vector=query_vector,
            k_nearest_neighbors=top_k,
            fields="content_vector",
        )

        select_fields = ["document_name", "chunk_id", "page_number", "content"]

        try:
            # Hybrid Search: search_text (BM25) + vector_queries (HNSW)
            raw_results = self.search_client.search(
                search_text=cleaned_query,
                vector_queries=[vector_query],
                select=select_fields,
                top=top_k,
            )
        except Exception as hybrid_err:
            # Fallback 1: Vector-only search
            try:
                raw_results = self.search_client.search(
                    search_text=None,
                    vector_queries=[vector_query],
                    select=select_fields,
                    top=top_k,
                )
            except Exception:
                # Fallback 2: Text-only search
                raw_results = self.search_client.search(
                    search_text=cleaned_query,
                    select=select_fields,
                    top=top_k,
                )

        chunks: List[Dict[str, Any]] = []
        for result in raw_results:
            chunks.append({
                "document_name": result.get("document_name", ""),
                "chunk_id": result.get("chunk_id", ""),
                "page_number": result.get("page_number", 0),
                "content": result.get("content", ""),
                "score": result.get("@search.score", 0.0),
            })

        return chunks


# Standalone function for tool calling and simple importing
def search_company_documents(query: str, top_k: int = 4) -> List[Dict[str, Any]]:
    """
    Search helper function for agent and API services.
    Retrieves the top-k most relevant document chunks using hybrid search.
    """
    service = SearchService()
    return service.search(query=query, top_k=top_k)


if __name__ == "__main__":
    print("=" * 65)
    print(" Azure AI Search - Hybrid Query Diagnostic & Quality Check")
    print("=" * 65)

    service = SearchService()
    test_queries = [
        
        "How many days of annual leave do employees get?",
        "What are the remote work rules and home office stipend?",
        "What is the notice period required for resignation?",
        "What is the company's policy on expense reports for client dinners?",
    ]

    for idx, q in enumerate(test_queries, start=1):
        print(f"\n[Query {idx}/3] \"{q}\"")
        print("-" * 65)
        results = service.search(query=q, top_k=4)

        if not results:
            print("  No chunks found.")
            continue

        print(f"  Retrieved {len(results)} top chunk(s):")
        for c_idx, chunk in enumerate(results, start=1):
            print(f"\n  Result #{c_idx} (Score: {chunk['score']:.4f})")
            print(f"    Document: {chunk['document_name']} | Page: {chunk['page_number']} | Chunk ID: {chunk['chunk_id']}")
            snippet = chunk["content"].replace("\n", " ").strip()
            print(f"    Excerpt:  {snippet[:220]}...")

    print("\n" + "=" * 65)
    print(" Hybrid Search Quality Check Complete.")
    print("=" * 65)
