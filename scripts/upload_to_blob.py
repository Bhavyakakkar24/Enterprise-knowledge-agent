"""
scripts/upload_to_blob.py - Upload Documents to Azure Blob Storage

Finds all PDF documents in data/sample_docs/, uploads them to the configured
Azure Blob Storage container (overwriting existing blobs), and lists all current
blobs in the container with their sizes.
"""

import sys
from pathlib import Path

# Add project root directory to Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config
from services.blob_service import BlobService


def format_size(size_bytes: int) -> str:
    """Formats bytes into human-readable size string (KB, MB, or Bytes)."""
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.2f} KB"
    return f"{size_bytes} Bytes"


def main():
    print("=" * 65)
    print(" Azure Blob Storage - Document Upload & Inventory")
    print("=" * 65)

    docs_dir = PROJECT_ROOT / "data" / "sample_docs"
    print(f"Target Container:  {config.AZURE_STORAGE_CONTAINER_NAME}")
    print(f"Source Directory:  {docs_dir.relative_to(PROJECT_ROOT)}")
    print("-" * 65)

    # 1. Validate Source Directory
    if not docs_dir.exists():
        print(f"[ERROR] Source folder does not exist: {docs_dir}")
        print("Please create the folder 'data/sample_docs/' and add your PDF files.")
        return

    # 2. Find PDF files in data/sample_docs/
    pdf_files = sorted(
        [f for f in docs_dir.iterdir() if f.is_file() and f.suffix.lower() == ".pdf"]
    )

    # 3. Initialize Blob Service & Ensure Container Exists
    try:
        blob_service = BlobService()
        blob_service.ensure_container_exists()
    except ValueError as e:
        print(f"[ERROR] Configuration error: {e}")
        return
    except PermissionError as e:
        print(f"[ERROR 401/403] Authentication failed when connecting to Azure Blob Storage.")
        print(f"  Details: {e}")
        print("  Fix: Please verify AZURE_STORAGE_CONNECTION_STRING in your .env file.")
        return
    except Exception as e:
        print(f"[ERROR] Failed to connect to Azure Blob Storage: {e}")
        return

    # 4. Upload PDF files
    if not pdf_files:
        print("[WARNING] No PDF files found in 'data/sample_docs/'.")
        print("  (If you created sample_hr_policy.md, please export or convert it to .pdf)")
    else:
        print(f"\n[Step 1/2] Uploading {len(pdf_files)} PDF file(s) (overwrite enabled)...")
        for pdf in pdf_files:
            try:
                result = blob_service.upload_file(pdf, overwrite=True)
                print(f"  [UPLOADED] {pdf.name} ({format_size(result['size_bytes'])}) -> container '{result['container']}'")
            except Exception as e:
                print(f"  [FAILED] Failed to upload {pdf.name}: {e}")

    # 5. List all blobs in the container with sizes
    print("\n[Step 2/2] Current Inventory in Blob Container:")
    try:
        blobs = blob_service.list_blobs()
        if not blobs:
            print(f"  (Container '{config.AZURE_STORAGE_CONTAINER_NAME}' is currently empty)")
        else:
            print(f"  {'Blob Name':<40} {'Size':<15} {'Last Modified'}")
            print(f"  {'-' * 38:<40} {'-' * 13:<15} {'-' * 20}")
            for b in blobs:
                mod_time = b["last_modified"].strftime("%Y-%m-%d %H:%M:%S UTC") if b["last_modified"] else "N/A"
                print(f"  {b['name']:<40} {format_size(b['size_bytes']):<15} {mod_time}")
            print(f"\n  Total Blobs in Container: {len(blobs)}")
    except Exception as e:
        print(f"[ERROR] Failed to list blobs in container: {e}")

    print("\n" + "=" * 65)
    print(" Operation Complete.")
    print("=" * 65)


if __name__ == "__main__":
    main()
