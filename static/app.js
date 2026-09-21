/**
 * static/app.js - Nexus Enterprise Knowledge Assistant Client
 * 
 * Handles user interactions, REST communication with /api/chat,
 * multi-turn conversation memory, secure DOM rendering, in-bubble
 * animated typing indicator, and smooth auto-scroll.
 */

document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const chatWrapper = document.getElementById("chat-wrapper");
    const messagesContainer = document.getElementById("messages-container");
    const chatForm = document.getElementById("chat-form");
    const chatInput = document.getElementById("chat-input");
    const sendButton = document.getElementById("send-button");
    const clearChatBtn = document.getElementById("clear-chat-btn");
    const welcomeHero = document.getElementById("welcome-hero");
    const quickPrompts = document.getElementById("quick-prompts");

    // In-memory conversation history state for the current session
    let conversationHistory = [];
    let isSubmitting = false;

    // Auto-focus input on page load
    chatInput.focus();

    /**
     * Smoothly scrolls the chat viewport to the newest message.
     */
    function scrollToBottom() {
        requestAnimationFrame(() => {
            chatWrapper.scrollTo({
                top: chatWrapper.scrollHeight,
                behavior: "smooth"
            });
        });
    }

    /**
     * Auto-adjusts textarea height based on content length.
     */
    chatInput.addEventListener("input", () => {
        chatInput.style.height = "auto";
        const newHeight = Math.min(chatInput.scrollHeight, 120);
        chatInput.style.height = newHeight + "px";
    });

    /**
     * Handles keyboard shortcuts:
     * - Enter: Submit question
     * - Shift + Enter: Multi-line newline
     */
    chatInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            chatForm.dispatchEvent(new Event("submit", { cancelable: true }));
        }
    });

    /**
     * Populates input and focuses when an example question chip is clicked.
     * @param {string} question Text of the example question.
     */
    function selectPrompt(question) {
        if (!question || isSubmitting) return;
        chatInput.value = question;
        chatInput.style.height = "auto";
        chatInput.focus();
    }

    // Attach click listeners to all suggestion & quick prompt chips
    document.querySelectorAll(".suggestion-chip, .quick-prompt-btn").forEach((chip) => {
        chip.addEventListener("click", () => {
            const question = chip.getAttribute("data-question");
            selectPrompt(question);
        });
    });

    /**
     * Clears all message history in the DOM and resets the conversationHistory state.
     */
    clearChatBtn.addEventListener("click", () => {
        if (isSubmitting) return;

        // Reset in-memory conversation memory
        conversationHistory = [];

        // Remove all message rows & error cards
        const messageRows = messagesContainer.querySelectorAll(".message-row, .error-card");
        messageRows.forEach((row) => row.remove());

        // Restore empty-state guidance
        if (welcomeHero) {
            welcomeHero.style.display = "block";
        }
        if (quickPrompts) {
            quickPrompts.classList.remove("hidden");
        }

        chatInput.value = "";
        chatInput.style.height = "auto";
        chatInput.focus();
        scrollToBottom();
    });

    /**
     * Helper to create the distinct Nexus "N" monogram avatar element.
     */
    function createAssistantAvatar() {
        const avatar = document.createElement("div");
        avatar.className = "avatar assistant-avatar";
        avatar.setAttribute("aria-hidden", "true");
        avatar.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M5 4V20L19 4V20" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
        return avatar;
    }

    /**
     * Helper to create the User avatar element.
     */
    function createUserAvatar() {
        const avatar = document.createElement("div");
        avatar.className = "avatar user-avatar";
        avatar.setAttribute("aria-hidden", "true");
        avatar.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>`;
        return avatar;
    }

    /**
     * Safely creates and appends a User Message Bubble to the DOM.
     * @param {string} text User question text.
     */
    function appendUserMessage(text) {
        if (welcomeHero) {
            welcomeHero.style.display = "none";
        }
        if (quickPrompts) {
            quickPrompts.classList.add("hidden");
        }

        const row = document.createElement("div");
        row.className = "message-row user";

        const bubbleContent = document.createElement("div");
        bubbleContent.className = "bubble-content";

        const bubble = document.createElement("div");
        bubble.className = "message-bubble";
        bubble.textContent = text; // Safe text rendering

        bubbleContent.appendChild(bubble);
        row.appendChild(createUserAvatar());
        row.appendChild(bubbleContent);

        messagesContainer.appendChild(row);
        scrollToBottom();
    }

    /**
     * Creates and appends an Assistant Message Bubble containing 3 pulsing loading dots.
     * @returns {HTMLElement} The loading row element to remove when response arrives.
     */
    function appendLoadingBubble() {
        const row = document.createElement("div");
        row.className = "message-row assistant loading-row";
        row.id = "active-loading-row";
        row.setAttribute("aria-live", "polite");

        const bubbleContent = document.createElement("div");
        bubbleContent.className = "bubble-content";

        const bubble = document.createElement("div");
        bubble.className = "message-bubble";

        const dotsContainer = document.createElement("div");
        dotsContainer.className = "typing-dots";
        dotsContainer.setAttribute("aria-label", "Nexus is searching documents and thinking");

        for (let i = 0; i < 3; i++) {
            const dot = document.createElement("span");
            dot.className = "dot";
            dotsContainer.appendChild(dot);
        }

        bubble.appendChild(dotsContainer);
        bubbleContent.appendChild(bubble);

        row.appendChild(createAssistantAvatar());
        row.appendChild(bubbleContent);

        messagesContainer.appendChild(row);
        scrollToBottom();
        return row;
    }

    /**
     * Safely creates and appends an Assistant Message Bubble with optional collapsible sources.
     * @param {string} answer Assistant text response.
     * @param {Array} sources Array of source objects { document, chunk_id, page_number }.
     */
    function appendAssistantMessage(answer, sources) {
        const row = document.createElement("div");
        row.className = "message-row assistant";

        const bubbleContent = document.createElement("div");
        bubbleContent.className = "bubble-content";

        const bubble = document.createElement("div");
        bubble.className = "message-bubble";
        bubble.textContent = answer; // Safe text rendering without innerHTML

        bubbleContent.appendChild(bubble);

        // Render Collapsible Sources if any were retrieved and used
        if (Array.isArray(sources) && sources.length > 0) {
            const sourcesDetails = document.createElement("details");
            sourcesDetails.className = "sources-card";

            const summary = document.createElement("summary");
            summary.textContent = `Sources & References (${sources.length})`;
            sourcesDetails.appendChild(summary);

            const sourcesList = document.createElement("ul");
            sourcesList.className = "sources-list";

            sources.forEach((src) => {
                const item = document.createElement("li");
                item.className = "source-item";

                const badge = document.createElement("span");
                badge.className = "source-doc-badge";
                badge.textContent = `📄 ${src.document || "Document"}`;
                if (src.page_number) {
                    badge.textContent += ` (Page ${src.page_number})`;
                }

                const chunkTag = document.createElement("span");
                chunkTag.className = "source-chunk-tag";
                chunkTag.textContent = src.chunk_id || "";

                item.appendChild(badge);
                item.appendChild(chunkTag);
                sourcesList.appendChild(item);
            });

            sourcesDetails.appendChild(sourcesList);
            bubbleContent.appendChild(sourcesDetails);
        }

        row.appendChild(createAssistantAvatar());
        row.appendChild(bubbleContent);

        messagesContainer.appendChild(row);
        scrollToBottom();
    }

    /**
     * Safely creates and displays a readable error message card.
     * @param {string} errorMessage Error explanation string.
     */
    function appendErrorMessage(errorMessage) {
        const errorCard = document.createElement("div");
        errorCard.className = "error-card";
        errorCard.setAttribute("role", "alert");

        const icon = document.createElement("div");
        icon.className = "error-icon";
        icon.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`;

        const textSpan = document.createElement("span");
        textSpan.textContent = errorMessage || "An unexpected error occurred. Please try again.";

        errorCard.appendChild(icon);
        errorCard.appendChild(textSpan);

        messagesContainer.appendChild(errorCard);
        scrollToBottom();
    }

    /**
     * Main Form Submit Handler: Sends question and conversation history to /api/chat via fetch()
     */
    chatForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        if (isSubmitting) return;

        const question = chatInput.value.trim();
        if (!question) {
            return;
        }

        // 1. Render User Message
        appendUserMessage(question);

        // 2. Clear input & reset height
        chatInput.value = "";
        chatInput.style.height = "auto";

        // 3. Show In-Bubble Loading State
        isSubmitting = true;
        sendButton.disabled = true;
        chatInput.disabled = true;
        const loadingRow = appendLoadingBubble();

        try {
            // 4. Send POST request with question and current conversation history
            const response = await fetch("/api/chat", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    question: question,
                    history: conversationHistory
                })
            });

            const data = await response.json();

            // Remove loading indicator bubble
            if (loadingRow && loadingRow.parentNode) {
                loadingRow.remove();
            }

            if (!response.ok) {
                // Server returned 4xx or 5xx error JSON
                const errorMsg = data.error || `Server error (${response.status})`;
                appendErrorMessage(errorMsg);
            } else {
                // Success 200 OK: Render assistant response and sources
                const answer = data.answer || "No response received.";
                const sources = Array.isArray(data.sources) ? data.sources : [];

                // Append assistant message bubble
                appendAssistantMessage(answer, sources);

                // Update in-memory session history for subsequent follow-up turns
                conversationHistory.push({ role: "user", content: question });
                conversationHistory.push({ role: "assistant", content: answer });

                // Keep only the last 10 turns (20 messages) to avoid payload bloat
                if (conversationHistory.length > 20) {
                    conversationHistory = conversationHistory.slice(-20);
                }
            }
        } catch (networkError) {
            if (loadingRow && loadingRow.parentNode) {
                loadingRow.remove();
            }
            console.error("Network or parsing error:", networkError);
            appendErrorMessage("Unable to connect to the assistant server. Please verify your connection.");
        } finally {
            // 5. Restore form controls
            isSubmitting = false;
            sendButton.disabled = false;
            chatInput.disabled = false;
            chatInput.focus();
            scrollToBottom();
        }
    });
});
