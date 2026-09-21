"""
services/agent_service.py - Custom AI Agent Loop with Tool Calling & Conversation Memory

Implements a custom agent loop using Azure OpenAI chat completions, multi-turn
conversation history support, and model function calling (search_company_documents)
capped at 3 iterations.
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

from openai import AzureOpenAI, APIError, AuthenticationError, RateLimitError

# Add project root directory to Python path if run standalone
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from services.search_service import search_company_documents


def normalize_azure_endpoint(endpoint: str) -> str:
    """Extracts base Azure endpoint without REST suffixes."""
    cleaned = endpoint.strip().rstrip("/")
    if "/openai" in cleaned:
        cleaned = cleaned.split("/openai")[0]
    return cleaned


SYSTEM_PROMPT = """You are Nexus, the official internal Enterprise AI Assistant for Acme Corp.
Your primary role is to assist employees by answering questions accurately based on official company documentation.

Core Guidelines:
1. Company-Specific Questions: When asked about company policies, benefits, leave, remote work, equipment, notice periods, working hours, expenses, or procedures, you MUST call the `search_company_documents` tool to retrieve verified facts before answering.
2. Conversation Context: You have access to the recent conversation history. When the user asks follow-up questions (e.g. "Can I carry over days?", "What about part-time?", "Yes", "Explain more"), use the prior context and search if needed to provide a coherent continuation.
3. General Questions: Answer general greetings, math, or common knowledge questions directly without calling the search tool.
4. Strict Grounding: NEVER hallucinate, guess, or invent company policies. Base all company-related answers strictly on the retrieved document excerpts.
5. Missing Information: If the retrieved documents do not contain the answer, state clearly: "I could not find information regarding that in the available company documentation." Do not guess or assume.
6. Tone: Maintain a professional, concise, and helpful tone.
"""

# Tool definition for Azure OpenAI Function Calling
AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_company_documents",
            "description": "Searches the internal enterprise knowledge base for official company policies, employee benefits, guidelines, working hours, remote work rules, and HR procedures.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Specific search query or keyword phrase to find relevant company document chunks in Azure AI Search.",
                    }
                },
                "required": ["query"],
            },
        },
    }
]

MAX_TOOL_CALL_ITERATIONS = 3
MAX_QUESTION_LENGTH = 1000
MAX_HISTORY_TURNS = 10


def is_not_found_response(answer: str) -> bool:
    """
    Checks if the assistant's answer indicates that information was not found,
    not documented, or out of scope, in which case sources must be empty.
    """
    if not answer:
        return True

    lower = answer.lower()
    not_found_phrases = [
        "could not find",
        "couldn't find",
        "cannot find",
        "can't find",
        "no information",
        "not found in",
        "not available in",
        "not mentioned in",
        "not covered in",
        "no mention of",
        "does not contain",
        "do not contain",
        "does not mention",
        "do not mention",
        "does not provide",
        "do not provide",
        "no policy regarding",
        "no policy on",
        "not specified in",
        "unable to find",
        "out of scope",
    ]
    return any(phrase in lower for phrase in not_found_phrases)


class AgentService:
    """Custom Agent Service that manages the model reasoning, conversation context, and tool-calling loop."""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        api_version: Optional[str] = None,
        chat_deployment: Optional[str] = None,
    ):
        raw_endpoint = endpoint or config.AZURE_OPENAI_ENDPOINT
        self.endpoint = normalize_azure_endpoint(raw_endpoint)
        self.api_key = api_key or config.AZURE_OPENAI_API_KEY
        self.api_version = api_version or config.AZURE_OPENAI_API_VERSION or "2024-02-15-preview"
        self.chat_deployment = chat_deployment or config.AZURE_OPENAI_CHAT_DEPLOYMENT

        self.client = AzureOpenAI(
            azure_endpoint=self.endpoint,
            api_key=self.api_key,
            api_version=self.api_version,
        )

    def validate_question(self, question: Any) -> str:
        """Validates user question input."""
        if question is None or not isinstance(question, str):
            raise ValueError("The 'question' parameter must be a non-empty string.")

        cleaned = question.strip()
        if not cleaned:
            raise ValueError("The 'question' parameter cannot be empty or whitespace only.")

        if len(cleaned) > MAX_QUESTION_LENGTH:
            raise ValueError(
                f"Question exceeds maximum allowed length of {MAX_QUESTION_LENGTH} characters."
            )

        return cleaned

    def sanitize_history(self, history: Any, max_turns: int = MAX_HISTORY_TURNS) -> List[Dict[str, str]]:
        """
        Validates and sanitizes multi-turn conversation history.
        Only keeps valid user/assistant message dictionaries.
        """
        if not history or not isinstance(history, list):
            return []

        sanitized = []
        for item in history:
            if isinstance(item, dict):
                role = item.get("role")
                content = item.get("content")
                if role in ("user", "assistant") and isinstance(content, str) and content.strip():
                    sanitized.append({
                        "role": role,
                        "content": content.strip()[: MAX_QUESTION_LENGTH * 2],
                    })

        return sanitized[-max_turns:]

    def answer_question(
        self,
        question: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Executes the custom agent loop with conversation history support:
        1. Prepares messages with system prompt, conversation history, and latest user question.
        2. Calls Azure OpenAI chat deployment with system prompt and search tool.
        3. If model requests tool calls, executes search_company_documents and feeds results back.
        4. Repeats until a final text answer is produced or max iterations reached.
        5. Constructs grounded sources list only if the answer actually uses retrieved context.
        """
        valid_question = self.validate_question(question)
        sanitized_history = self.sanitize_history(history)

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]

        # Append sanitized conversation history
        for h_msg in sanitized_history:
            messages.append({"role": h_msg["role"], "content": h_msg["content"]})

        # Append current user question
        messages.append({"role": "user", "content": valid_question})

        retrieved_sources: List[Dict[str, Any]] = []
        seen_chunk_ids = set()
        iterations = 0

        while iterations < MAX_TOOL_CALL_ITERATIONS:
            iterations += 1

            response = self.client.chat.completions.create(
                model=self.chat_deployment,
                messages=messages,
                tools=AGENT_TOOLS,
                tool_choice="auto",
                temperature=0.2,
            )

            choice = response.choices[0]
            message = choice.message

            # Append assistant message to conversation history
            messages.append(message)

            # If the model does not request any tool calls, it has returned its final response
            if not message.tool_calls:
                final_answer = message.content or ""
                sources = [] if is_not_found_response(final_answer) else retrieved_sources
                return {
                    "answer": final_answer,
                    "sources": sources,
                }

            # Handle Tool Calls requested by the model
            for tool_call in message.tool_calls:
                function_name = tool_call.function.name
                arguments_str = tool_call.function.arguments

                if function_name == "search_company_documents":
                    try:
                        args = json.loads(arguments_str)
                        search_query = args.get("query", valid_question)
                    except Exception:
                        search_query = valid_question

                    # Execute Azure AI Search
                    search_results = search_company_documents(query=search_query, top_k=4)

                    # Track verified sources
                    for chunk in search_results:
                        c_id = chunk.get("chunk_id")
                        if c_id and c_id not in seen_chunk_ids:
                            seen_chunk_ids.add(c_id)
                            retrieved_sources.append({
                                "document": chunk.get("document_name", "unknown"),
                                "chunk_id": c_id,
                                "page_number": chunk.get("page_number", 1),
                            })

                    # Prepare tool response content for the model
                    tool_content = json.dumps([
                        {
                            "chunk_id": r.get("chunk_id"),
                            "document_name": r.get("document_name"),
                            "page_number": r.get("page_number"),
                            "content": r.get("content"),
                        }
                        for r in search_results
                    ])

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": function_name,
                        "content": tool_content,
                    })
                else:
                    # Unknown tool fallback
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": function_name,
                        "content": json.dumps({"error": f"Unknown tool '{function_name}'"}),
                    })

        # If loop reached max iterations without concluding, make one final call without tools
        final_response = self.client.chat.completions.create(
            model=self.chat_deployment,
            messages=messages,
            temperature=0.2,
        )

        final_answer = final_response.choices[0].message.content or ""
        sources = [] if is_not_found_response(final_answer) else retrieved_sources

        return {
            "answer": final_answer,
            "sources": sources,
        }


# Standalone function for easy routing and testing
def run_agent(
    question: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Helper function to execute the custom agent loop for a question with optional history."""
    service = AgentService()
    return service.answer_question(question, history=history)
