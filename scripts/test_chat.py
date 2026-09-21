"""
scripts/test_chat.py - AI Agent Chat Test Diagnostic

Tests 3 distinct categories of questions:
1. A company policy question (requires search_company_documents tool call).
2. A general knowledge question (answered directly without search tool).
3. An unanswerable question (grounded agent states lack of documentation).
"""

import json
import sys
from pathlib import Path

# Add project root directory to Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from services.agent_service import AgentService


def run_chat_test():
    print("=" * 65)
    print(" Enterprise Agent - Chat & Tool Calling Verification")
    print("=" * 65)

    agent = AgentService()

    test_cases = [
        {
            "category": "Company Policy Question",
            "question": "How many days of paid annual leave do full-time employees receive at Acme Corp?",
            "expected_behavior": "Should invoke search_company_documents and answer 25 days with sources.",
        },
        {
            "category": "General Knowledge Question",
            "question": "What is the capital of France?",
            "expected_behavior": "Should answer Paris directly without calling the search tool.",
        },
        {
            "category": "Unanswerable / Out-of-Scope Question",
            "question": "What is Acme Corp's official policy on bringing pet dragons to the office?",
            "expected_behavior": "Should search or recognize lack of policy and state information was not found.",
        },
    ]

    for index, tc in enumerate(test_cases, start=1):
        print(f"\n[Test {index}/3] Category: {tc['category']}")
        print(f"Question: \"{tc['question']}\"")
        print(f"Expected: {tc['expected_behavior']}")
        print("-" * 65)

        try:
            response = agent.answer_question(tc["question"])
            print("Response JSON:")
            print(json.dumps(response, indent=2))
        except Exception as e:
            print(f"[ERROR] Failed to get response: {e}")

    print("\n" + "=" * 65)
    print(" Chat Verification Complete.")
    print("=" * 65)


if __name__ == "__main__":
    run_chat_test()
