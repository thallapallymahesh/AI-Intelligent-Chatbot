SYSTEM_MESSAGE = {
    "role": "system",
    "content": (
        "You are a helpful and intelligent AI assistant. "
        "Give clear, accurate and useful answers."
    ),
}

RECENT_MESSAGE_LIMIT = 6


def build_chat_messages(recent_messages, user_message, document_context):
    """Build a temporary Ollama context for one chat request."""

    messages = [SYSTEM_MESSAGE.copy()]

    messages.extend(
        {"role": role, "content": content} for role, content in recent_messages
    )

    messages.append(
        {
            "role": "user",
            "content": (
                f"Relevant document context:\n"
                f"{document_context}\n\n"
                f"User question:\n"
                f"{user_message}\n\n"
                "Use the document context when "
                "it is relevant to the question."
            ),
        }
    )

    return messages
