"""
scripts/ingest.py - End-to-End PDF Ingestion Pipeline

Workflow:
1. Downloads PDF documents from Azure Blob Storage.
2. Extracts text and chunks documents using DocumentProcessor.
3. Generates 1536-dimensional vector embeddings using EmbeddingService.
4. Ensures Azure AI Search index exists with PROJECT_CONTEXT.md schema.
5. Uploads / merges chunks into Azure AI Search. Safe to rerun without duplication.
"""

import sys
from pathlib import Path

# Add project root directory to Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config
from services.blob_service import BlobService
from services.document_processor import DocumentProcessor
from services.embedding_service import EmbeddingService
from services.search_service import SearchService


def main():
    print("=" * 65)
    print(" Enterprise Ingestion Pipeline (Blob -> Chunks -> Embed -> Search)")
    print("=" * 65)

    print(f"Blob Container:      {config.AZURE_STORAGE_CONTAINER_NAME}")
    print(f"Search Index:        {config.AZURE_SEARCH_INDEX_NAME}")
    print(f"Embedding Model:     {config.AZURE_OPENAI_EMBEDDING_DEPLOYMENT}")
    print(f"Vector Dimensions:   {config.AZURE_OPENAI_EMBEDDING_DIMENSIONS}")
    print("-" * 65)

    # 1. Connect to Blob Storage and discover PDF files
    print("\n[Step 1/5] Discovering documents in Azure Blob Storage...")
    try:
        blob_service = BlobService()
        all_blobs = blob_service.list_blobs()
        pdf_blobs = [b for b in all_blobs if b["name"].lower().endswith(".pdf")]
    except Exception as e:
        print(f"[ERROR] Failed to list blobs from container: {e}")
        return

    if not pdf_blobs:
        print(f"[WARNING] No PDF files found in Blob container '{config.AZURE_STORAGE_CONTAINER_NAME}'.")
        print("  Please run 'python scripts/upload_to_blob.py' first to upload documents.")
        return

    print(f"  Found {len(pdf_blobs)} PDF document(s) in Blob Storage:")
    for b in pdf_blobs:
        print(f"  - {b['name']} ({b['size_bytes']} bytes)")

    # 2. Ensure Azure AI Search index exists
    print("\n[Step 2/5] Initializing Azure AI Search index...")
    try:
        search_service = SearchService()
        index = search_service.create_or_update_index()
        print(f"  [SUCCESS] Search index '{index.name}' is ready.")
    except Exception as e:
        print(f"[ERROR] Failed to create or update search index: {e}")
        return

    # 3. Process documents, generate chunks, embed, and upload
    processor = DocumentProcessor(chunk_size=900, chunk_overlap=150)
    embedding_service = EmbeddingService()

    total_chunks_processed = 0
    total_chunks_uploaded = 0

    for idx, blob_info in enumerate(pdf_blobs, start=1):
        blob_name = blob_info["name"]
        print(f"\n[Step 3/5 - Doc {idx}/{len(pdf_blobs)}] Processing '{blob_name}'...")

        # Download blob in memory
        try:
            pdf_bytes = blob_service.get_blob_bytes(blob_name)
            print(f"  Downloaded {len(pdf_bytes)} bytes from Blob Storage.")
        except Exception as e:
            print(f"  [FAILED] Failed to download '{blob_name}': {e}")
            continue

        # Extract & Chunk
        try:
            chunks = processor.process_pdf(pdf_bytes, document_name=blob_name)
            print(f"  Extracted {len(chunks)} text chunks (approx. 900 chars each with 150 char overlap).")
        except Exception as e:
            print(f"  [FAILED] Failed to process PDF text: {e}")
            continue

        if not chunks:
            print(f"  [WARNING] No text chunks extracted from '{blob_name}'.")
            continue

        # Generate Embeddings in Batches
        print(f"\n[Step 4/5 - Doc {idx}/{len(pdf_blobs)}] Generating vector embeddings...")
        try:
            embedded_chunks = embedding_service.embed_chunks(chunks, batch_size=16)
            print(f"  Generated 1536-d embeddings for {len(embedded_chunks)} chunks.")
        except Exception as e:
            print(f"  [FAILED] Embedding generation failed: {e}")
            continue

        # Upload to Azure AI Search
        print(f"\n[Step 5/5 - Doc {idx}/{len(pdf_blobs)}] Uploading chunks to Azure AI Search...")
        try:
            uploaded_count = search_service.upload_chunks(embedded_chunks, batch_size=50)
            print(f"  [UPLOADED] {uploaded_count}/{len(embedded_chunks)} chunks indexed in '{config.AZURE_SEARCH_INDEX_NAME}'.")
            total_chunks_processed += len(chunks)
            total_chunks_uploaded += uploaded_count
        except Exception as e:
            print(f"  [FAILED] Failed to upload chunks to Azure AI Search: {e}")

    # Summary
    print("\n" + "=" * 65)
    print(" Ingestion Summary")
    print("=" * 65)
    print(f"Documents Ingested:      {len(pdf_blobs)}")
    print(f"Total Chunks Generated:  {total_chunks_processed}")
    print(f"Total Chunks Uploaded:   {total_chunks_uploaded}")
    print(f"Target Search Index:     {config.AZURE_SEARCH_INDEX_NAME}")
    print("=" * 65)


if __name__ == "__main__":
    main()
