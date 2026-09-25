import { useState, useEffect } from "react";
import "./App.css";

const API_URL = "http://127.0.0.1:8000";

function App() {
  // --------------------------------------------------
  // State
  // --------------------------------------------------

  const [chats, setChats] = useState([]);
  const [currentChatId, setCurrentChatId] = useState(null);

  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content:
        "Hello! 👋 I'm your AI Intelligent Assistant. How can I help you today?",
    },
  ]);

  const [input, setInput] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [serviceStatus, setServiceStatus] = useState("checking");

  const checkHealth = async () => {
    try {
      const response = await fetch(`${API_URL}/api/health`);
      const data = await response.json();
      setServiceStatus(response.ok && data.status === "healthy" ? "online" : "degraded");
    } catch {
      setServiceStatus("offline");
    }
  };

  // --------------------------------------------------
  // Load all chats
  // --------------------------------------------------

  const loadChats = async () => {
    try {
      const response = await fetch(`${API_URL}/api/chats`);

      if (!response.ok) {
        throw new Error("Failed to load chats");
      }

      const data = await response.json();

      setChats(data.chats || []);
    } catch (error) {
      console.error("Failed to load chats:", error);
    }
  };

  // --------------------------------------------------
  // Load chats when application starts
  // --------------------------------------------------

  useEffect(() => {
    loadChats();
    checkHealth();
  }, []);

  // --------------------------------------------------
  // Create New Chat
  // --------------------------------------------------

  const createNewChat = async () => {
    if (sending || uploading) return;

    try {
      console.log("Creating new chat...");

      const response = await fetch(`${API_URL}/api/new-chat`, {
        method: "POST",
        headers: {
          Accept: "application/json",
        },
      });

      console.log("New chat response:", response.status);

      if (!response.ok) {
        const errorText = await response.text();
        console.error("New chat backend error:", errorText);

        throw new Error("Failed to create new chat");
      }

      const data = await response.json().catch(() => ({}));

      console.log("New chat created:", data);

      const newChat = {
        id: data.chat_id,
        title: data.title || "New Conversation",
        created_at: new Date().toISOString(),
      };

      // Put newest chat at the top
      setChats((prev) => [newChat, ...prev]);

      // Make this the active chat
      setCurrentChatId(data.chat_id);

      // Reset messages
      setMessages([
        {
          role: "assistant",
          content:
            "Hello! 👋 I'm your AI Intelligent Assistant. How can I help you today?",
        },
      ]);

      setInput("");
      setUploadMessage("");

      // Refresh sidebar
      await loadChats();
    } catch (error) {
      console.error("Failed to create new chat:", error);

      setMessages([
        {
          role: "assistant",
          content:
            "Unable to create a new chat. Please make sure the backend is running.",
        },
      ]);
    }
  };

  // --------------------------------------------------
  // Load Selected Chat
  // --------------------------------------------------

  const loadChat = async (chatId) => {
    try {
      console.log("Loading chat:", chatId);

      const response = await fetch(`${API_URL}/api/chats/${chatId}`);

      if (!response.ok) {
        const errorText = await response.text();
        console.error("Load chat backend error:", errorText);

        throw new Error("Failed to load chat");
      }

      const data = await response.json();

      console.log("Chat loaded:", data);

      setCurrentChatId(chatId);

      setMessages(
        data.messages && data.messages.length > 0
          ? data.messages
          : [
              {
                role: "assistant",
                content:
                  "Hello! 👋 I'm your AI Intelligent Assistant. How can I help you today?",
              },
            ],
      );

      setInput("");
      setUploadMessage("");
    } catch (error) {
      console.error("Failed to load chat:", error);

      setMessages([
        {
          role: "assistant",
          content: "Unable to load this conversation.",
        },
      ]);
    }
  };

  // --------------------------------------------------
  // Upload Document
  // --------------------------------------------------

  const uploadDocument = async (file) => {
    if (!file) return;

    // User should have an active chat
    if (!currentChatId) {
      setUploadMessage("Please click + New Chat first.");
      return;
    }

    setUploading(true);
    setUploadMessage("");

    const formData = new FormData();
    formData.append("file", file);
    formData.append("chat_id", currentChatId);

    try {
      console.log("Uploading document:", file.name);

      const response = await fetch(`${API_URL}/api/upload`, {
        method: "POST",
        body: formData,
      });

      const data = await response.json();

      console.log("Upload response:", data);

      if (!response.ok) {
        throw new Error(data.detail || "Upload failed. Please try again.");
      }

      setUploadMessage(
        `✅ ${data.filename} uploaded successfully (${data.chunks} chunks)`,
      );
    } catch (error) {
      console.error("Upload error:", error);

      setUploadMessage(`❌ ${error.message}`);
    } finally {
      setUploading(false);
    }
  };

  // --------------------------------------------------
  // Send Message
  // --------------------------------------------------

  const sendMessage = async () => {
    if (!input.trim()) return;

    // User must create/select a chat first
    if (!currentChatId) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Please click + New Chat first, then ask your question.",
        },
      ]);

      return;
    }

    if (sending) return;

    const currentInput = input.trim();

    // Show user's message immediately
    setMessages((prev) => [
      ...prev,
      {
        role: "user",
        content: currentInput,
      },
    ]);

    setInput("");
    setSending(true);
    setUploadMessage("");

    try {
      console.log("Sending message...");
      console.log("Chat ID:", currentChatId);
      console.log("Message:", currentInput);

      const response = await fetch(`${API_URL}/api/chat`, {
        method: "POST",

        headers: {
          "Content-Type": "application/json",
          Accept: "application/x-ndjson",
        },

        body: JSON.stringify({
          message: currentInput,
          chat_id: currentChatId,
        }),
      });

      console.log("Chat response status:", response.status);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Backend request failed (${response.status}).`);
      }

      if (!response.body) {
        throw new Error("Response body is empty");
      }

      // --------------------------------------------------
      // Add empty assistant message
      // --------------------------------------------------

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "",
        },
      ]);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      let buffer = "";

      // --------------------------------------------------
      // Read streaming response
      // --------------------------------------------------

      while (true) {
        const { value, done } = await reader.read();

        if (done) break;

        buffer += decoder.decode(value, {
          stream: true,
        });

        const lines = buffer.split("\n");

        // Keep incomplete line for next chunk
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.trim()) continue;

          try {
            const data = JSON.parse(line);

            // --------------------------------------------------
            // AI token
            // --------------------------------------------------

            if (data.token) {
              setMessages((prev) => {
                const updated = [...prev];

                const lastIndex = updated.length - 1;

                if (lastIndex >= 0 && updated[lastIndex].role === "assistant") {
                  updated[lastIndex] = {
                    ...updated[lastIndex],
                    content: updated[lastIndex].content + data.token,
                  };
                }

                return updated;
              });
            }

            // --------------------------------------------------
            // Document sources
            // --------------------------------------------------

            if (data.sources) {
              setMessages((prev) => {
                const updated = [...prev];

                const lastIndex = updated.length - 1;

                if (lastIndex >= 0 && updated[lastIndex].role === "assistant") {
                  updated[lastIndex] = {
                    ...updated[lastIndex],
                    sources: data.sources,
                  };
                }

                return updated;
              });
            }

            if (data.error) {
              setMessages((prev) => {
                const updated = [...prev];
                const lastIndex = updated.length - 1;
                if (lastIndex >= 0 && updated[lastIndex].role === "assistant") {
                  updated[lastIndex] = { ...updated[lastIndex], content: data.error };
                }
                return updated;
              });
            }
          } catch (error) {
            console.error("Streaming parse error:", error);
          }
        }
      }

      // --------------------------------------------------
      // Process remaining buffer
      // --------------------------------------------------

      if (buffer.trim()) {
        try {
          const data = JSON.parse(buffer);

          if (data.token) {
            setMessages((prev) => {
              const updated = [...prev];

              const lastIndex = updated.length - 1;

              if (lastIndex >= 0 && updated[lastIndex].role === "assistant") {
                updated[lastIndex] = {
                  ...updated[lastIndex],
                  content: updated[lastIndex].content + data.token,
                };
              }

              return updated;
            });
          }

          if (data.sources) {
            setMessages((prev) => {
              const updated = [...prev];

              const lastIndex = updated.length - 1;

              if (lastIndex >= 0 && updated[lastIndex].role === "assistant") {
                updated[lastIndex] = {
                  ...updated[lastIndex],
                  sources: data.sources,
                };
              }

              return updated;
            });
          }

          if (data.error) {
            setMessages((prev) => {
              const updated = [...prev];
              const lastIndex = updated.length - 1;
              if (lastIndex >= 0 && updated[lastIndex].role === "assistant") {
                updated[lastIndex] = { ...updated[lastIndex], content: data.error };
              }
              return updated;
            });
          }
        } catch (error) {
          console.error("Final streaming parse error:", error);
        }
      }

      // --------------------------------------------------
      // Refresh sidebar
      // --------------------------------------------------

      await loadChats();
    } catch (error) {
      console.error("Chat error:", error);

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Unable to send your message: ${error.message}`,
        },
      ]);
    } finally {
      setSending(false);
    }
  };

  // --------------------------------------------------
  // Enter key
  // --------------------------------------------------

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  // --------------------------------------------------
  // UI
  // --------------------------------------------------

  return (
    <div className="app">
      {/* --------------------------------------------------
          Sidebar
      -------------------------------------------------- */}

      <aside className="sidebar">
        <div className="logo">
          🤖 <span>AI Assistant</span>
        </div>

        {/* New Chat Button */}

        <button
          className="new-chat"
          onClick={createNewChat}
          disabled={sending || uploading}
        >
          + New Chat
        </button>

        {/* Chat History */}

        <div className="chat-history">
          <p className="history-title">Recent Chats</p>

          {chats.length === 0 ? (
            <p className="no-chats">No conversations yet</p>
          ) : (
            chats.map((chat) => (
              <div
                key={chat.id}
                className={`history-item ${
                  currentChatId === chat.id ? "active" : ""
                }`}
                onClick={() => loadChat(chat.id)}
              >
                💬 {chat.title}
              </div>
            ))
          )}
        </div>

        {/* Sidebar Bottom */}

        <div className="sidebar-bottom">
          <button>⚙️ Settings</button>

          <button>❓ Help</button>
        </div>
      </aside>

      {/* --------------------------------------------------
          Main Chat
      -------------------------------------------------- */}

      <main className="chat-container">
        {/* Header */}

        <header className="chat-header">
          <div>
            <h1>AI Intelligent Assistant</h1>

            <p>
              <span className="status-dot"></span>
              {serviceStatus === "online"
                ? "Online"
                : serviceStatus === "checking"
                  ? "Checking service..."
                  : serviceStatus === "degraded"
                    ? "Service needs attention"
                    : "Backend unavailable"}
            </p>
          </div>
        </header>

        {/* --------------------------------------------------
            Messages
        -------------------------------------------------- */}

        <section className="messages">
          {messages.map((message, index) => (
            <div key={index} className={`message-row ${message.role}`}>
              {/* Avatar */}

              <div className="avatar">
                {message.role === "assistant" ? "🤖" : "👤"}
              </div>

              {/* Message */}

              <div className="message">
                {message.content}

                {/* --------------------------------------------------
                    Sources
                -------------------------------------------------- */}

                {message.sources && message.sources.length > 0 && (
                  <div className="sources">
                    <div className="sources-title">📚 Sources</div>

                    {message.sources.map((source, sourceIndex) => (
                      <div className="source-item" key={sourceIndex}>
                        📄 {source.filename}
                        <span> — Chunk {source.chunk + 1}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}

          {/* Typing indicator */}

          {sending && (
            <div className="message-row assistant">
              <div className="avatar">🤖</div>

              <div className="message">
                <span>Thinking...</span>
              </div>
            </div>
          )}
        </section>

        {/* --------------------------------------------------
            Input Area
        -------------------------------------------------- */}

        <div className="input-area">
          <div className="input-box">
            {/* File Upload */}

            <label className="attach-button">
              📎
              <input
                type="file"
                accept=".pdf,.docx,.txt"
                style={{
                  display: "none",
                }}
                disabled={uploading}
                onChange={(e) => {
                  uploadDocument(e.target.files[0]);

                  e.target.value = "";
                }}
              />
            </label>

            {/* Text Input */}

            <input
              type="text"
              placeholder={
                currentChatId ? "Ask anything..." : "Click + New Chat first..."
              }
              value={input}
              disabled={sending}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
            />

            {/* Send Button */}

            <button
              className="send-button"
              onClick={sendMessage}
              disabled={sending || !input.trim() || !currentChatId}
            >
              ➤
            </button>
          </div>

          {/* Bottom Message */}

          <p className="input-note">
            {uploading
              ? "📤 Uploading and processing document..."
              : uploadMessage ||
                (sending
                  ? "🤖 AI is generating a response..."
                  : currentChatId
                    ? "AI can make mistakes. Verify important information."
                    : "Click + New Chat to start a conversation.")}
          </p>
        </div>
      </main>
    </div>
  );
}

export default App;
