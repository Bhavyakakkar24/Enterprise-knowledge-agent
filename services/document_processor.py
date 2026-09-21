"""
services/document_processor.py - PDF Extraction and Text Chunking Service

Extracts text page-by-page from PDF documents using pypdf and splits
text into overlapping chunks formatted for Azure AI Search ingestion.
"""

import re
import sys
import io
from pathlib import Path
from typing import List, Dict, Any, Union, Optional
import pypdf

# Add project root directory to Python path if run standalone
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class DocumentProcessor:
    """Service to extract text from PDFs and produce overlapping chunks with metadata."""

    def __init__(self, chunk_size: int = 900, chunk_overlap: int = 150):
        """
        :param chunk_size: Target maximum character length for each chunk (approx. 800-1000 chars).
        :param chunk_overlap: Number of overlapping characters between consecutive chunks.
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def extract_pages_from_pdf(
        self, pdf_source: Union[str, Path, bytes, io.BytesIO]
    ) -> List[Dict[str, Any]]:
        """
        Extracts text from each page of a PDF document.

        :param pdf_source: File path, Path object, bytes, or BytesIO stream of the PDF.
        :return: List of dicts with 'page_number' (1-indexed) and 'text'.
        """
        if isinstance(pdf_source, (str, Path)):
            path = Path(pdf_source)
            if not path.exists():
                raise FileNotFoundError(f"PDF file not found: {path}")
            reader = pypdf.PdfReader(str(path))
        elif isinstance(pdf_source, bytes):
            reader = pypdf.PdfReader(io.BytesIO(pdf_source))
        elif isinstance(pdf_source, io.BytesIO):
            reader = pypdf.PdfReader(pdf_source)
        else:
            raise TypeError("Unsupported PDF source type. Provide a file path, bytes, or BytesIO.")

        pages_data = []
        for index, page in enumerate(reader.pages):
            page_num = index + 1
            extracted = page.extract_text() or ""
            cleaned = extracted.strip()
            if cleaned:
                pages_data.append({
                    "page_number": page_num,
                    "text": cleaned,
                })

        return pages_data

    def chunk_text(self, text: str) -> List[str]:
        """
        Splits a string of text into chunks of approximately `chunk_size` characters
        with `chunk_overlap` characters of overlap between consecutive chunks.

        Breaks on natural boundaries (newlines, sentence punctuation, or spaces)
        to prevent cutting words or sentences in half.
        """
        cleaned_text = text.strip()
        if not cleaned_text:
            return []

        if len(cleaned_text) <= self.chunk_size:
            return [cleaned_text]

        chunks = []
        start = 0
        total_length = len(cleaned_text)

        while start < total_length:
            end = start + self.chunk_size

            # If reaching the end of the text, grab remainder
            if end >= total_length:
                chunk = cleaned_text[start:total_length].strip()
                if chunk:
                    chunks.append(chunk)
                break

            # Find best split point near the end of the window (within last 120 chars)
            split_idx = -1
            for separator in ["\n\n", "\n", ". ", "? ", "! "]:
                idx = cleaned_text.rfind(separator, start + self.chunk_size - 120, end)
                if idx != -1:
                    split_idx = idx + len(separator)
                    break

            # Fallback to last space if no sentence punctuation found
            if split_idx == -1:
                space_idx = cleaned_text.rfind(" ", start + self.chunk_size - 100, end)
                if space_idx != -1:
                    split_idx = space_idx + 1
                else:
                    split_idx = end

            chunk = cleaned_text[start:split_idx].strip()
            if chunk:
                chunks.append(chunk)

            # Move start index forward considering overlap
            next_start = split_idx - self.chunk_overlap
            if next_start <= start:
                next_start = split_idx  # Ensure forward progress
            start = next_start

        return chunks

    def process_pdf(
        self,
        pdf_source: Union[str, Path, bytes, io.BytesIO],
        document_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Extracts pages from a PDF and splits each page into chunks with complete metadata
        matching the Azure AI Search index schema.

        :param pdf_source: File path, Path object, bytes, or BytesIO stream of the PDF.
        :param document_name: Optional filename identifier.
        :return: List of chunk dictionaries containing:
                 - id: Sanitized primary key for search index
                 - document_name: Original file name
                 - chunk_id: Unique chunk identifier
                 - page_number: 1-indexed page number
                 - content: Chunk text
                 - source: Source identifier
        """
        doc_name = document_name
        if not doc_name:
            if isinstance(pdf_source, (str, Path)):
                doc_name = Path(pdf_source).name
            else:
                doc_name = "document.pdf"

        # Safe key format for Azure Search (letters, digits, _, -, =)
        safe_doc_id = re.sub(r"[^a-zA-Z0-9_\-=]", "_", doc_name)

        pages = self.extract_pages_from_pdf(pdf_source)
        all_chunks = []
        chunk_counter = 1

        for page in pages:
            page_num = page["page_number"]
            page_chunks = self.chunk_text(page["text"])

            for idx, chunk_text in enumerate(page_chunks):
                chunk_id = f"{doc_name}_p{page_num}_c{idx + 1:03d}"
                doc_key = f"{safe_doc_id}_p{page_num}_c{idx + 1:03d}"

                all_chunks.append({
                    "id": doc_key,
                    "document_name": doc_name,
                    "chunk_id": chunk_id,
                    "page_number": page_num,
                    "content": chunk_text,
                    "source": doc_name,
                })
                chunk_counter += 1

        return all_chunks


if __name__ == "__main__":
    print("=" * 65)
    print(" Document Processor - Self Test")
    print("=" * 65)

    sample_pdf_path = PROJECT_ROOT / "data" / "sample_docs" / "sample_hr_policy.pdf"

    if not sample_pdf_path.exists():
        print(f"[ERROR] Sample PDF not found at {sample_pdf_path}")
        sys.exit(1)

    processor = DocumentProcessor(chunk_size=900, chunk_overlap=150)
    chunks = processor.process_pdf(sample_pdf_path)

    print(f"File Processed:   {sample_pdf_path.name}")
    print(f"Total Chunks:     {len(chunks)}")
    print("-" * 65)

    if chunks:
        example = chunks[0]
        print("Example Chunk [0]:")
        print(f"  id:            {example['id']}")
        print(f"  document_name: {example['document_name']}")
        print(f"  chunk_id:      {example['chunk_id']}")
        print(f"  page_number:   {example['page_number']}")
        print(f"  content length:{len(example['content'])} characters")
        print(f"  source:        {example['source']}")
        print("\n--- Chunk Content Preview ---")
        print(example["content"])
        print("-----------------------------")

    print("\n" + "=" * 65)
    print(" Self Test Finished.")
    print("=" * 65)
