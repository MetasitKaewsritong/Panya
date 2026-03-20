import { useState, useEffect, useRef, useCallback } from "react";

import {
  Plus,
  Send,
  MessageSquareText,
  LoaderCircle,
  LogOut,
  Bot,
  Trash2,
  PanelLeftClose,
  PanelLeft,
  Menu,
  Mic,
  MicOff,
  Ear,
  Pin,
  Search,
  X,
  Copy,
  Check,
  CornerDownLeft,
  StopCircle
} from "lucide-react";

// Centralized API and hooks
import api from "../utils/api";
import { useVoiceRecording } from "../hooks/useVoiceRecording";

import {
  formatTime,
  mapServerMessage
} from "../utils/formatters";
import Sidebar from "../components/chat/Sidebar";
import ChatInput from "../components/chat/ChatInput";
import MessageBubble from "../components/chat/MessageBubble";

function Chat({ onLogout }) {
  /* ================= STATE ================= */
  const [user, setUser] = useState({ full_name: "User", name: "User" });
  const [chatHistory, setChatHistory] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);
  const [isNewChat, setIsNewChat] = useState(false);

  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [isMobile, setIsMobile] = useState(false);

  // Pinned chats (stored in localStorage)
  const [pinnedChats, setPinnedChats] = useState(() => {
    const saved = localStorage.getItem('pinnedChats');
    return saved ? JSON.parse(saved) : [];
  });

  // Search state
  const [searchQuery, setSearchQuery] = useState("");

  // Copy state
  const [copiedMessageId, setCopiedMessageId] = useState(null);

  // Pagination state
  const [chatPagination, setChatPagination] = useState({}); // { sessionId: { hasMore, total, offset } }
  const [loadingMore, setLoadingMore] = useState(false);
  const [useVisionMode, setUseVisionMode] = useState(() => {
    const stored = localStorage.getItem("chat_use_vision_mode");
    return stored === "true";
  });
  const useVisionModeRef = useRef(useVisionMode);

  const chatEndRef = useRef(null);
  const inputRef = useRef(null);
  const abortControllerRef = useRef(null);

  useEffect(() => {
    useVisionModeRef.current = useVisionMode;
    localStorage.setItem("chat_use_vision_mode", String(useVisionMode));
  }, [useVisionMode]);

  const setAnswerMode = useCallback((mode) => {
    const nextIsVision = mode === "vision";
    useVisionModeRef.current = nextIsVision;
    setUseVisionMode(nextIsVision);
  }, []);

  // Voice recording hook
  const {
    isRecording,
    isTranscribing,
    startRecording,
    stopRecording,
    cancelTranscription
  } = useVoiceRecording((text) => {
    setInput(prev => prev + (prev ? ' ' : '') + text);
    // Delay focus until after React re-renders with isTranscribing=false
    setTimeout(() => inputRef.current?.focus(), 50);
  });

  // Copy to clipboard function
  const copyToClipboard = async (text, messageId) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedMessageId(messageId);
      setTimeout(() => setCopiedMessageId(null), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  /* ================= MOBILE DETECTION & AUTO-COLLAPSE ================= */
  useEffect(() => {
    const checkMobile = () => {
      const mobile = window.innerWidth < 768;
      setIsMobile(mobile);
      if (mobile) {
        setSidebarCollapsed(true);
      }
    };

    checkMobile(); // Check on mount
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  /* ================= LOAD USER ================= */
  useEffect(() => {
    api.get("/api/auth/me")
      .then(res => setUser(res.data))
      .catch(err => console.error("Failed to load user:", err));
  }, []);

  /* ================= LOAD SESSIONS ================= */
  useEffect(() => {
    api.get("/api/chat/sessions")
      .then(res => {
        const sessions = res.data.items.map(s => ({
          id: s.id,
          title: s.title,
          messages: [],
          created_at: s.created_at,
          updated_at: s.updated_at || s.created_at,
        }));
        setChatHistory(sessions);
      })
      .catch(console.error);
  }, []);

  /* ================= LOAD MESSAGES ================= */
  useEffect(() => {
    if (!activeChatId) return;

    const currentChat = chatHistory.find(c => c.id === activeChatId);
    if (currentChat && currentChat.messages.length > 0) return;

    api.get(`/api/chat/sessions/${activeChatId}`)
      .then(res => {
        const messages = res.data.items.map(mapServerMessage);

        setChatHistory(prev =>
          prev.map(c =>
            c.id === activeChatId ? { ...c, messages } : c
          )
        );

        // Track pagination state
        setChatPagination(prev => ({
          ...prev,
          [activeChatId]: {
            hasMore: res.data.has_more,
            total: res.data.total,
            offset: res.data.items.length,
          }
        }));
      })
      .catch(err => {
        // Session not found or error - log for debugging
        console.error("Failed to load messages:", err);
      });
  }, [activeChatId, chatHistory]);

  /* ================= LOAD MORE MESSAGES ================= */
  const loadMoreMessages = async () => {
    if (!activeChatId || loadingMore) return;

    const pagination = chatPagination[activeChatId];
    if (!pagination?.hasMore) return;

    setLoadingMore(true);
    try {
      const res = await api.get(`/api/chat/sessions/${activeChatId}?offset=${pagination.offset}`);
      const olderMessages = res.data.items.map(mapServerMessage);

      setChatHistory(prev =>
        prev.map(c =>
          c.id === activeChatId
            ? { ...c, messages: [...olderMessages, ...c.messages] }
            : c
        )
      );

      setChatPagination(prev => ({
        ...prev,
        [activeChatId]: {
          ...prev[activeChatId],
          hasMore: res.data.has_more,
          offset: prev[activeChatId].offset + res.data.items.length,
        }
      }));
    } catch (err) {
      console.error('Failed to load more messages:', err);
    } finally {
      setLoadingMore(false);
    }
  };

  useEffect(() => {
    if (!activeChatId) return;

    const activeChat = chatHistory.find(c => c.id === activeChatId);
    const hasPendingRagas = Boolean(
      activeChat?.messages?.some(m => m.sender === "bot" && m.ragasStatus === "pending")
    );
    if (!hasPendingRagas) return;

    const intervalId = window.setInterval(() => {
      api.get(`/api/chat/sessions/${activeChatId}`)
        .then(res => {
          const messages = res.data.items.map(mapServerMessage);
          setChatHistory(prev =>
            prev.map(c =>
              c.id === activeChatId ? { ...c, messages } : c
            )
          );
        })
        .catch(err => console.error("Failed to refresh pending RAGAS:", err));
    }, 5000);

    return () => window.clearInterval(intervalId);
  }, [activeChatId, chatHistory]);

  /* ================= HANDLERS ================= */

  const handleNewChat = () => {
    setActiveChatId(null);
    setIsNewChat(true);
  };

  // Temporary state to show first message in new chat before session is created
  const [pendingMessage, setPendingMessage] = useState(null);

  // Handle Enter key on input: voice activation, stop recording, or send
  const handleInputKeyDown = useCallback((e) => {
    if (e.key !== 'Enter') return;

    // Enter while recording → stop recording
    if (isRecording) {
      e.preventDefault();
      stopRecording();
      return;
    }

    // Enter while loading → cancel the question
    if (isLoading) {
      e.preventDefault();
      abortControllerRef.current?.abort();
      return;
    }

    // Enter while transcribing → cancel transcription and focus chatbox
    if (isTranscribing) {
      e.preventDefault();
      cancelTranscription();
      // Focus the input after cancellation
      setTimeout(() => {
        inputRef.current?.focus();
      }, 0);
      return;
    }

    // Read current value from the ref to avoid stale closures
    const currentValue = inputRef.current?.value || '';

    // Enter with empty input → start voice recording
    if (!currentValue.trim()) {
      e.preventDefault();
      startRecording();
      return;
    }

    // Otherwise let Enter propagate naturally → form onSubmit fires
  }, [isRecording, isTranscribing, isLoading, startRecording, stopRecording, cancelTranscription]);

  const handleSendMessage = useCallback(async (e) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;
    const requestedVisionMode = useVisionModeRef.current;

    const userMessage = { text: input, sender: "user", timestamp: new Date().toISOString() };
    setInput("");
    setIsLoading(true);

    // Optimistically Add User Message
    if (activeChatId) {
      setChatHistory(prev =>
        prev.map(c =>
          c.id === activeChatId
            ? { ...c, messages: [...c.messages, userMessage] }
            : c
        )
      );
    } else {
      setPendingMessage(userMessage);
    }

    let createdSessionId = null;
    let userCancelled = false;

    try {
      // Use fetch for streaming (axios doesn't support it well in browser)
      const token = localStorage.getItem("access_token");
      const currentSessionId = isNewChat ? null : activeChatId;
      createdSessionId = currentSessionId;

      // Create AbortController for cancellation support
      const abortController = new AbortController();
      abortControllerRef.current = abortController;
      const origAbort = abortController.abort.bind(abortController);
      abortController.abort = (...args) => { userCancelled = true; origAbort(...args); };

      const response = await fetch(`${api.defaults.baseURL}/api/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({
          message: userMessage.text,
          session_id: currentSessionId,
          use_page_images: requestedVisionMode,
        }),
        signal: abortController.signal
      });

      if (!response.ok) throw new Error("Stream failed");

      // Setup Bot Message Placeholder
      const botMessage = {
        text: "",
        sender: "bot",
        timestamp: new Date().toISOString(),
        isStreaming: true,
        processingTime: null,
        retrievalTime: null,
        llmTime: null,
        contextCount: null,
        sources: [],
        sourceDetails: [],
        collection: "plcnext",
        answerSupportStatus: null,
        responseMode: requestedVisionMode ? "vision" : "text",
        requestedMode: requestedVisionMode ? "vision" : "text",
        modeFallbackReason: null,
      };

      // If existing chat, add placeholder now
      if (!isNewChat && activeChatId) {
        setChatHistory(prev => prev.map(c =>
          c.id === activeChatId ? { ...c, messages: [...c.messages, botMessage] } : c
        ));
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      let streamDone = false;
      while (!streamDone) {
        const { value, done } = await reader.read();
        if (done) {
          streamDone = true;
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || ""; // Keep last partial line

        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const event = JSON.parse(line);

            if (event.type === "session") {
              createdSessionId = event.id;

              // If this was a new chat, we need to create the session in state now
              if (isNewChat) {
                const newSession = {
                  id: createdSessionId,
                  title: userMessage.text.substring(0, 50),
                  messages: [userMessage, botMessage],
                  created_at: new Date().toISOString(),
                  updated_at: new Date().toISOString(),
                };
                setChatHistory(prev => [newSession, ...prev]);
                setActiveChatId(createdSessionId);
                setIsNewChat(false);
                setPendingMessage(null);
              }
            } else if (event.type === "token") {
              // Update text - ensure event.text is always a string
              const tokenText = typeof event.text === 'string' ? event.text : String(event.text || '');
              setChatHistory(prev => prev.map(c => {
                if (c.id === createdSessionId) {
                  const msgs = [...c.messages];
                  const last = msgs[msgs.length - 1];
                  if (last.sender === 'bot') {
                    const currentText = typeof last.text === 'string' ? last.text : String(last.text || '');
                    msgs[msgs.length - 1] = { ...last, text: currentText + tokenText };
                    return { ...c, messages: msgs };
                  }
                }
                return c;
              }));
            } else if (event.type === "context") {
              setChatHistory(prev => prev.map(c => {
                if (c.id !== createdSessionId) return c;

                const msgs = [...c.messages];
                const last = msgs[msgs.length - 1];
                if (!last || last.sender !== "bot") return c;

                msgs[msgs.length - 1] = {
                  ...last,
                  contextCount: event.doc_count ?? last.contextCount ?? null,
                  sources: Array.isArray(event.sources) ? event.sources : last.sources || [],
                  sourceDetails: Array.isArray(event.page_references) ? event.page_references : last.sourceDetails || [],
                };
                return { ...c, messages: msgs };
              }));
            } else if (event.type === "stats") {
              const stats = event.data;
              setChatHistory(prev => prev.map(c => {
                if (c.id === createdSessionId) {
                  const msgs = [...c.messages];
                  const last = msgs[msgs.length - 1];
                  const finalText = stats.full_reply || last.text;
                  msgs[msgs.length - 1] = {
                    ...last,
                    processingTime: stats.processing_time,
                    retrievalTime: stats.retrieval_time,
                    llmTime: stats.llm_time,
                    contextCount: stats.context_count ?? null,
                    sources: Array.isArray(stats.sources) ? stats.sources : last.sources || [],
                    sourceDetails: Array.isArray(stats.source_details) ? stats.source_details : last.sourceDetails || [],
                    collection: stats.collection || last.collection || "plcnext",
                    ragas: stats.ragas || null,
                    ragasStatus: stats.ragas_status || null,
                    responseMode: stats.response_mode || last.responseMode || null,
                    requestedMode: stats.requested_mode || last.requestedMode || null,
                    modeFallbackReason: stats.mode_fallback_reason || null,
                    answerSupportStatus: stats.answer_support_status || null,
                    intentQuery: stats.intent_query || null,
                    intentSource: stats.intent_source || null,
                    intentDetails: stats.intent_details || null,
                    // Ensure text is final and is a string
                    text: typeof finalText === 'string' ? finalText : String(finalText || ''),
                    isStreaming: false
                  };
                  return { ...c, messages: msgs, updated_at: new Date().toISOString() };
                }
                return c;
              }));
            }
          } catch (e) {
            console.error("Stream parse error", e, line);
          }
        }

        // Auto-scroll
        chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
      }

    } catch (error) {
      console.error("Chat error:", error);

      const isCancelled = error.name === 'AbortError' && userCancelled;
      const errorText = isCancelled
        ? "This question was cancelled."
        : "Sorry, I encountered an error. Please try again.";
      const targetId = createdSessionId || activeChatId;

      if (targetId) {
        setPendingMessage(null);
        setChatHistory(prev => prev.map(c => {
          if (c.id !== targetId) return c;

          // Remove any in-progress bot message (streaming placeholder)
          const cleaned = c.messages.filter(m => !m.isStreaming || m.text);

          return {
            ...c,
            messages: [...cleaned, {
              sender: 'bot',
              text: errorText,
              timestamp: new Date().toISOString(),
              isCancelled: isCancelled,
            }]
          };
        }));
      } else {
        // New chat where session ID was never received — show an error
        // via a temporary chat so the user sees feedback.
        const tempId = `temp-error-${Date.now()}`;
        const errorSession = {
          id: tempId,
          title: userMessage.text.substring(0, 50) || "New Chat",
          messages: [
            userMessage,
            {
              sender: 'bot',
              text: errorText,
              timestamp: new Date().toISOString(),
              isCancelled: isCancelled,
            }
          ],
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        setChatHistory(prev => [errorSession, ...prev]);
        setActiveChatId(tempId);
        setIsNewChat(false);
        setPendingMessage(null);
      }
    } finally {
      setIsLoading(false);
      abortControllerRef.current = null;
      setTimeout(() => {
        chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
        inputRef.current?.focus();
      }, 100);
    }
  }, [input, isLoading, activeChatId, isNewChat]);

  /* ================= CHAT PINNING ================= */

  const togglePin = (e, chatId) => {
    e.stopPropagation();
    setPinnedChats(prev => {
      const newPinned = prev.includes(chatId)
        ? prev.filter(id => id !== chatId)
        : [...prev, chatId];
      localStorage.setItem('pinnedChats', JSON.stringify(newPinned));
      return newPinned;
    });
  };

  // Filter and sort chats: filter by search, then pinned first
  const sortedChatHistory = [...chatHistory]
    .filter(chat => {
      if (!searchQuery.trim()) return true;
      return (chat.title || '').toLowerCase().includes(searchQuery.toLowerCase());
    })
    .sort((a, b) => {
      const aPinned = pinnedChats.includes(a.id);
      const bPinned = pinnedChats.includes(b.id);
      if (aPinned && !bPinned) return -1;
      if (!aPinned && bPinned) return 1;
      return 0; // Keep original order within groups
    });

  /* ================= SESSION MANAGEMENT (RENAME / DELETE) ================= */

  // 1. Delete Session
  const handleDeleteSession = async (e, sessionId) => {
    e.stopPropagation();

    try {
      await api.delete(`/api/chat/sessions/${sessionId}`);
      setChatHistory(prev => prev.filter(c => c.id !== sessionId));

      if (activeChatId === sessionId) {
        setActiveChatId(null);
        setIsNewChat(true);
      }
    } catch (error) {
      console.error("Delete failed", error);
    }
  };



  const activeChat = chatHistory.find(c => c.id === activeChatId);
  const isEmptyChat = (isNewChat || !activeChatId) && !isLoading && !pendingMessage;

  /* ================= UI ================= */
  return (
    <div className="flex h-screen bg-gray-100 font-sans relative">

      {/* ===== MOBILE BACKDROP ===== */}
      {isMobile && !sidebarCollapsed && (
        <div
          className="fixed inset-0 bg-black/50 z-40"
          onClick={() => setSidebarCollapsed(true)}
        />
      )}

      {/* ===== SIDEBAR ===== */}
      <Sidebar 
        isMobile={isMobile}
        sidebarCollapsed={sidebarCollapsed}
        setSidebarCollapsed={setSidebarCollapsed}
        isLoading={isLoading}
        handleNewChat={handleNewChat}
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        sortedChatHistory={sortedChatHistory}
        activeChatId={activeChatId}
        setActiveChatId={setActiveChatId}
        setIsNewChat={setIsNewChat}
        pinnedChats={pinnedChats}
        togglePin={togglePin}
        handleDeleteSession={handleDeleteSession}
        user={user}
        onLogout={onLogout}
      />

      {/* ===== MAIN ===== */}
      <div className="flex-1 flex flex-col h-screen relative">

        {/* HEADER */}
        <header className="h-16 bg-white/80 backdrop-blur-md border-b flex items-center justify-between px-6 shrink-0 z-10 sticky top-0">

          {/* Mobile menu button + Title */}
          <div className="flex items-center gap-3">
            {/* Hamburger menu for mobile */}
            {isMobile && (
              <button
                onClick={(e) => { e.currentTarget.blur(); setSidebarCollapsed(false); }}
                className="p-2 hover:bg-gray-100 rounded-lg text-gray-600"
                title="Open menu"
              >
                <Menu size={20} />
              </button>
            )}
            <div className="flex flex-col">
              <span
                className="font-semibold text-gray-800 text-lg"
                title={activeChat ? activeChat.title : "New Chat"}
              >
                {activeChat
                  ? (activeChat.title && activeChat.title.length > 45
                    ? activeChat.title.substring(0, 45) + "..."
                    : activeChat.title || "New Chat")
                  : "New Chat"}
              </span>
            </div>
          </div>

        </header>

        {isEmptyChat ? (
          /* ===== CENTERED LAYOUT FOR NEW/EMPTY CHATS ===== */
          <div className="flex-1 flex flex-col items-center justify-center p-4 sm:p-6">
            <div className="flex flex-col items-center justify-center px-4 mb-8">
              {/* Avatar */}
              <div className="bg-gradient-to-br from-blue-500 to-blue-600 p-4 rounded-2xl shadow-lg mb-6">
                <Bot size={40} className="text-white" />
              </div>

              {/* Welcome Text */}
              <h2 className="text-2xl font-bold text-gray-800">Hi, I'm Panya! 👋</h2>
            </div>

            {/* Input Form - Centered */}
            <div className="w-full max-w-3xl px-4">
              <ChatInput
                handleSendMessage={handleSendMessage}
                setAnswerMode={setAnswerMode}
                isLoading={isLoading}
                useVisionMode={useVisionMode}
                inputRef={inputRef}
                input={input}
                setInput={setInput}
                isRecording={isRecording}
                isTranscribing={isTranscribing}
                handleInputKeyDown={handleInputKeyDown}
                cancelTranscription={cancelTranscription}
                stopRecording={stopRecording}
                startRecording={startRecording}
                abortControllerRef={abortControllerRef}
              />
              <div className="text-center text-[10px] text-gray-400 mt-3 font-medium">
                PLC Assistant can make mistakes. Check important info.
              </div>
            </div>
          </div>
        ) : (
          /* ===== NORMAL LAYOUT WITH MESSAGES ===== */
          <>
            <div className="flex-1 overflow-y-auto p-4 sm:p-6 scroll-smooth">
              <div className="max-w-3xl mx-auto flex flex-col gap-6 pb-4">

                {/* Load More Button */}
                {activeChatId && chatPagination[activeChatId]?.hasMore && (
                  <div className="flex justify-center py-3">
                    <button
                      onClick={(e) => { e.currentTarget.blur(); loadMoreMessages(); }}
                      disabled={loadingMore}
                      className="flex items-center gap-2 px-4 py-2 text-sm bg-gray-100 hover:bg-gray-200 text-gray-600 rounded-lg transition-all disabled:opacity-50"
                    >
                      {loadingMore ? (
                        <>
                          <LoaderCircle size={14} className="animate-spin" />
                          Loading...
                        </>
                      ) : (
                        "↑ Load older messages"
                      )}
                    </button>
                  </div>
                )}

                {activeChat?.messages.map((m, i) => (
                  <MessageBubble
                    key={i}
                    m={m}
                    index={i}
                    copiedMessageId={copiedMessageId}
                    copyToClipboard={copyToClipboard}
                    setInput={setInput}
                    inputRef={inputRef}
                  />
                ))}

                {/* Show pending message for new chat before session is created */}
                {pendingMessage && !activeChat && (
                  <div className="flex flex-col items-end">
                    <div
                      className="max-w-[85%] px-5 py-3.5 rounded-2xl shadow-sm text-[15px] leading-relaxed bg-gradient-to-r from-blue-600 to-blue-500 text-white rounded-br-sm break-words overflow-hidden"
                      style={{ overflowWrap: 'anywhere', wordBreak: 'break-word' }}
                    >
                      {pendingMessage.text}
                    </div>
                    {pendingMessage.timestamp && (
                      <span className="text-[10px] text-gray-400 mt-1 px-1">
                        {formatTime(pendingMessage.timestamp)}
                      </span>
                    )}
                  </div>
                )}



                <div ref={chatEndRef} />
              </div>
            </div>

            {/* INPUT AREA - Bottom pinned */}
            <div className="p-4 shrink-0">
              <ChatInput
                handleSendMessage={handleSendMessage}
                setAnswerMode={setAnswerMode}
                isLoading={isLoading}
                useVisionMode={useVisionMode}
                inputRef={inputRef}
                input={input}
                setInput={setInput}
                isRecording={isRecording}
                isTranscribing={isTranscribing}
                handleInputKeyDown={handleInputKeyDown}
                cancelTranscription={cancelTranscription}
                stopRecording={stopRecording}
                startRecording={startRecording}
                abortControllerRef={abortControllerRef}
              />
              <div className="text-center text-[10px] text-gray-400 mt-3 font-medium">
                PLC Assistant can make mistakes. Check important info.
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default Chat;
