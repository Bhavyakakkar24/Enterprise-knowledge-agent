"""
scripts/check_foundry.py - Connectivity & Sanity Check for Azure Foundry / OpenAI

Tests:
1. Chat Completion deployment connectivity and response.
2. Embedding deployment connectivity and vector dimension verification.
"""

import sys
from pathlib import Path

# Add project root directory to Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config
from openai import AzureOpenAI, APIError, AuthenticationError, NotFoundError, RateLimitError


def get_normalized_azure_endpoint(endpoint: str) -> str:
    """
    Normalizes Azure endpoint URL for the AzureOpenAI SDK.
    The SDK expects the base URL (e.g., https://<name>.services.ai.azure.com or
    https://<name>.openai.azure.com) without REST path suffixes like /openai/v1/responses.
    """
    cleaned = endpoint.strip().rstrip("/")
    if "/openai" in cleaned:
        cleaned = cleaned.split("/openai")[0]
    return cleaned


def main():
    print("=" * 65)
    print(" Azure AI Foundry (Azure OpenAI) Connectivity Diagnostic")
    print("=" * 65)

    raw_endpoint = config.AZURE_OPENAI_ENDPOINT
    base_endpoint = get_normalized_azure_endpoint(raw_endpoint)
    api_version = config.AZURE_OPENAI_API_VERSION or "2024-02-15-preview"

    print(f"Base Endpoint:      {base_endpoint}")
    print(f"API Version:        {api_version}")
    print(f"Chat Deployment:    {config.AZURE_OPENAI_CHAT_DEPLOYMENT}")
    print(f"Embedding Model:    {config.AZURE_OPENAI_EMBEDDING_DEPLOYMENT}")
    print("-" * 65)

    # Initialize Azure OpenAI Client
    try:
        client = AzureOpenAI(
            azure_endpoint=base_endpoint,
            api_key=config.AZURE_OPENAI_API_KEY,
            api_version=api_version,
        )
    except Exception as e:
        print(f"[ERROR] Failed to initialize AzureOpenAI client: {e}")
        return

    # 1. Test Chat Completion
    print("\n[Step 1/2] Testing Chat Deployment...")
    try:
        chat_prompt = "Say 'Foundry chat connection successful!' in one short sentence."
        response = client.chat.completions.create(
            model=config.AZURE_OPENAI_CHAT_DEPLOYMENT,
            messages=[
                {"role": "system", "content": "You are an enterprise knowledge assistant."},
                {"role": "user", "content": chat_prompt},
            ],
            max_tokens=50,
            temperature=0.7,
        )
        answer = response.choices[0].message.content.strip()
        print("[SUCCESS] Chat deployment responded:")
        print(f"  Response: \"{answer}\"")
    except AuthenticationError:
        print("[ERROR 401] Authentication failed. Check AZURE_OPENAI_API_KEY in .env.")
    except NotFoundError as e:
        print(f"[ERROR 404] Deployment or resource not found ({e}).")
        print(f"  Check AZURE_OPENAI_CHAT_DEPLOYMENT='{config.AZURE_OPENAI_CHAT_DEPLOYMENT}' and endpoint format.")
    except RateLimitError:
        print("[ERROR 429] Rate limit exceeded or quota exhausted for chat deployment.")
    except APIError as e:
        print(f"[ERROR] Azure OpenAI API error: {e}")
    except Exception as e:
        print(f"[ERROR] Unexpected error during chat request: {e}")

    # 2. Test Embedding Generation
    print("\n[Step 2/2] Testing Embedding Deployment...")
    try:
        sample_text = "Enterprise knowledge agent embedding check."
        embedding_res = client.embeddings.create(
            model=config.AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
            input=sample_text,
        )
        vector = embedding_res.data[0].embedding
        vector_len = len(vector)
        print("[SUCCESS] Embedding generated successfully:")
        print(f"  Vector length: {vector_len} dimensions")
        if vector_len == config.AZURE_OPENAI_EMBEDDING_DIMENSIONS:
            print(f"  Dimension matches expected configured size ({config.AZURE_OPENAI_EMBEDDING_DIMENSIONS}).")
        else:
            print(f"  [WARNING] Expected {config.AZURE_OPENAI_EMBEDDING_DIMENSIONS} dimensions, got {vector_len}.")
    except AuthenticationError:
        print("[ERROR 401] Authentication failed. Check AZURE_OPENAI_API_KEY in .env.")
    except NotFoundError as e:
        print(f"[ERROR 404] Embedding deployment not found ({e}).")
        print(f"  Check AZURE_OPENAI_EMBEDDING_DEPLOYMENT='{config.AZURE_OPENAI_EMBEDDING_DEPLOYMENT}' in .env.")
    except RateLimitError:
        print("[ERROR 429] Rate limit exceeded or quota exhausted for embedding deployment.")
    except APIError as e:
        print(f"[ERROR] Azure OpenAI API error: {e}")
    except Exception as e:
        print(f"[ERROR] Unexpected error during embedding request: {e}")

    print("\n" + "=" * 65)
    print(" Diagnostic Complete.")
    print("=" * 65)


if __name__ == "__main__":
    main()
