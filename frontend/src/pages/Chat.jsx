import { useState, useEffect, useRef, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
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

/* ================= HELPER FUNCTIONS ================= */
const formatTimeAgo = (timestamp) => {
  if (!timestamp) return '';
  const now = new Date();
  const time = new Date(timestamp);
  const diffMs = now - time;
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);

  if (diffSec < 60) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHour < 24) return `${diffHour}h ago`;
  if (diffDay === 1) return 'yesterday';
  if (diffDay < 7) return `${diffDay}d ago`;
  return time.toLocaleDateString();
};

const formatTime = (timestamp) => {
  if (!timestamp) return '';
  const time = new Date(timestamp);
  return time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
};

/**
 * Clean up malformed inline tables by converting them to proper markdown format.
 * This handles cases where tables are on a single line.
 */
const fixMarkdownTable = (text) => {
  if (!text || !text.includes('|')) return text;

  const lines = text.split('\n');
  const fixedLines = [];
  
  for (const line of lines) {
    // Check if this is an inline table (has separator pattern inline)
    // Pattern: | text | text | | --- | --- | | text | text |
    if (line.includes('| ---') && line.split('|').length > 8) {
      // This looks like an inline table, try to split it properly
      const parts = line.split('|').map(p => p.trim()).filter(p => p);
      
      // Find separator indices (cells that are just dashes)
      const sepIndices = [];
      parts.forEach((p, i) => {
        if (/^-+$/.test(p)) sepIndices.push(i);
      });
      
      if (sepIndices.length > 0) {
        const numCols = sepIndices[0];
        
        if (numCols > 0) {
          // Build proper table rows
          const rows = [];
          for (let i = 0; i < parts.length; i += numCols) {
            const rowParts = parts.slice(i, i + numCols);
            if (rowParts.length === numCols) {
              rows.push('| ' + rowParts.join(' | ') + ' |');
            }
          }
          
          if (rows.length > 0) {
            fixedLines.push(rows.join('\n'));
            continue;
          }
        }
      }
    }
    
    fixedLines.push(line);
  }
  
  return fixedLines.join('\n');
};

const stripQualityMetrics = (text) => {
  if (!text) return text;

  const lines = String(text).split('\n');
  const result = [];
  let skipSection = false;

  const isHorizontalRule = (line) => {
    const trimmed = line.trim();
    return trimmed === '---' || trimmed === '***' || trimmed === '___';
  };

  const markers = [
    'response quality metrics',
    '📊 response quality metrics',
    'overall quality',
    'answer relevancy',
    'faithfulness',
    'context precision',
    'context recall',
    'referenced documents',
    '📚 referenced documents'
  ];

  for (const line of lines) {
    const lower = line.toLowerCase();

    if (markers.some(marker => lower.includes(marker))) {
      // Remove a divider just before the metrics block
      if (result.length > 0 && isHorizontalRule(result[result.length - 1])) {
        result.pop();
      }
      skipSection = true;
      continue;
    }

    if (skipSection) {
      const isMetricLine = markers.some(marker => lower.includes(marker))
        || lower.includes('%')
        || lower.includes('.pdf')
        || lower.includes('pages')
        || line.trim().startsWith('•')
        || line.trim().startsWith('-')
        || isHorizontalRule(line);

      if (isMetricLine || line.trim() === '') {
        continue;
      }

      skipSection = false;
    }

    result.push(line);
  }

  return result.join('\n');
};

const RAGAS_METRIC_KEYS = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"];
const RAGAS_METRIC_LABELS = {
  faithfulness: "Faithfulness",
  answer_relevancy: "Answer Relevancy",
  context_precision: "Context Precision",
  context_recall: "Context Recall",
};

const formatRagasMetric = (value) => {
  if (value === null || value === undefined) return "N/A";
  const num = Number(value);
  if (Number.isNaN(num)) return "N/A";
  return `${(num * 100).toFixed(1)}%`;
};

const formatResponseMode = (mode) => {
  const value = String(mode || "").toLowerCase();
  if (value === "vision") return "Vision";
  if (value === "text") return "Text";
  return null;
};

const shouldShowVisionFallback = (message) => {
  const requested = String(message?.requestedMode || "").toLowerCase();
  const response = String(message?.responseMode || "").toLowerCase();
  return requested === "vision" && response !== "vision" && Boolean(message?.modeFallbackReason);
};



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

  const chatEndRef = useRef(null);
  const inputRef = useRef(null);
  const abortControllerRef = useRef(null);

  useEffect(() => {
    localStorage.setItem("chat_use_vision_mode", String(useVisionMode));
  }, [useVisionMode]);

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
        // If no active chat and sessions exist, select the first one.
        if (sessions.length > 0) {
          setActiveChatId(prev => prev ?? sessions[0].id);
        }
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
        const messages = res.data.items.map(m => ({
          text: m.content,
          sender: m.role === "user" ? "user" : "bot",
          timestamp: m.created_at,
          processingTime: m.metadata?.processing_time,
          ragas: m.metadata?.ragas || null,
          ragasStatus: m.metadata?.ragas_status || null,
          responseMode: m.metadata?.response_mode || null,
          requestedMode: m.metadata?.requested_mode || null,
          modeFallbackReason: m.metadata?.mode_fallback_reason || null,
        }));

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
      const olderMessages = res.data.items.map(m => ({
        text: m.content,
        sender: m.role === "user" ? "user" : "bot",
        timestamp: m.created_at,
        processingTime: m.metadata?.processing_time,
        ragas: m.metadata?.ragas || null,
        ragasStatus: m.metadata?.ragas_status || null,
        responseMode: m.metadata?.response_mode || null,
        requestedMode: m.metadata?.requested_mode || null,
        modeFallbackReason: m.metadata?.mode_fallback_reason || null,
      }));

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

    try {
      // Use fetch for streaming (axios doesn't support it well in browser)
      const token = localStorage.getItem("access_token");
      const currentSessionId = isNewChat ? null : activeChatId;
      createdSessionId = currentSessionId;

      // Create AbortController for cancellation support
      const abortController = new AbortController();
      abortControllerRef.current = abortController;

      const response = await fetch(`${api.defaults.baseURL}/api/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({
          message: userMessage.text,
          session_id: currentSessionId,
          use_page_images: useVisionMode,
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
        responseMode: useVisionMode ? "vision" : "text",
        requestedMode: useVisionMode ? "vision" : "text",
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
              // Context event - could show sources in future if needed
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
                    ragas: stats.ragas || null,
                    ragasStatus: stats.ragas_status || null,
                    responseMode: stats.response_mode || last.responseMode || null,
                    requestedMode: stats.requested_mode || last.requestedMode || null,
                    modeFallbackReason: stats.mode_fallback_reason || null,
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
      setPendingMessage(null);

      const isCancelled = error.name === 'AbortError';
      const targetId = createdSessionId || activeChatId;

      if (targetId) {
        setChatHistory(prev => prev.map(c => {
          if (c.id !== targetId) return c;

          // Remove any in-progress bot message (streaming placeholder)
          const cleaned = c.messages.filter(m => !m.isStreaming || m.text);

          return {
            ...c,
            messages: [...cleaned, {
              sender: 'bot',
              text: isCancelled
                ? "This question was cancelled."
                : "Sorry, I encountered an error. Please try again.",
              timestamp: new Date().toISOString(),
              isCancelled: isCancelled,
            }]
          };
        }));
      }
    } finally {
      setIsLoading(false);
      abortControllerRef.current = null;
      setTimeout(() => {
        chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
        inputRef.current?.focus();
      }, 100);
    }
  }, [input, isLoading, activeChatId, isNewChat, useVisionMode]);

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
      <aside className={`
        ${isMobile
          ? `fixed top-0 left-0 h-full z-50 transform transition-transform duration-200 ease-in-out ${sidebarCollapsed ? '-translate-x-full' : 'translate-x-0'} w-72`
          : `${sidebarCollapsed ? 'w-16' : 'w-72'} transition-[width] duration-200 ease-in-out`
        } 
        p-4 bg-white border-r flex flex-col overflow-hidden
      `}>
        {/* Header with Logo and Collapse Button */}
        <div className={`flex-shrink-0 mb-6 flex ${!isMobile && sidebarCollapsed ? 'flex-col items-center gap-2' : 'items-center justify-between'}`}>
          {/* Logo Area - Expanded (and always on mobile when open) */}
          {(isMobile || !sidebarCollapsed) && (
            <div className="flex items-center gap-3 px-2">
              <div className="bg-gradient-to-br from-blue-600 to-blue-700 p-2 rounded-xl shadow-lg shadow-gray-200">
                <Bot className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-lg font-bold text-gray-800 tracking-tight">PLC Assistant</h1>
                <p className="text-[11px] font-medium text-gray-400 uppercase tracking-wider">Industrial AI</p>
              </div>
            </div>
          )}
          {/* Collapsed Logo - Desktop only */}
          {!isMobile && sidebarCollapsed && (
            <div className="bg-gradient-to-br from-blue-600 to-blue-700 p-2 rounded-xl shadow-lg shadow-gray-200">
              <Bot className="w-6 h-6 text-white" />
            </div>
          )}
          {/* Collapse/Close Button */}
          <button
            onClick={(e) => { e.currentTarget.blur(); setSidebarCollapsed(!sidebarCollapsed); }}
            className="p-2 hover:bg-gray-100 rounded-lg transition-all text-gray-500 hover:text-gray-700"
            title={isMobile ? 'Close menu' : (sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar')}
          >
            {isMobile ? (
              <X size={20} />
            ) : (
              sidebarCollapsed ? <PanelLeft size={20} /> : <PanelLeftClose size={20} />
            )}
          </button>
        </div>

        {/* New Chat Button */}
        <button
          onClick={(e) => { e.currentTarget.blur(); handleNewChat(); }}
          disabled={isLoading}
          className={`flex items-center justify-center gap-2 w-full p-3 mb-4 bg-gradient-to-r from-blue-500 to-blue-600 text-white rounded-xl transition-all text-sm font-semibold shadow-md ${isLoading ? 'opacity-50 cursor-default' : 'hover:from-blue-600 hover:to-blue-700 hover:shadow-lg cursor-pointer'} ${!isMobile && sidebarCollapsed ? 'px-0' : ''}`}
          title="New Chat"
        >
          <Plus size={18} />
          {(isMobile || !sidebarCollapsed) && 'New Chat'}
        </button>

        {/* Search Box */}
        {(isMobile || !sidebarCollapsed) && (
          <div className="relative mb-3">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search chats..."
              disabled={isLoading}
              className={`w-full pl-9 pr-8 py-2 text-sm bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-300 ${isLoading ? 'opacity-50 cursor-default' : ''}`}
            />
            {searchQuery && (
              <button
                onClick={(e) => { e.currentTarget.blur(); setSearchQuery(""); }}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 hover:bg-gray-200 rounded text-gray-400 hover:text-gray-600"
              >
                <X size={14} />
              </button>
            )}
          </div>
        )}

        {/* Recent Label */}
        {(isMobile || !sidebarCollapsed) && (
          <div className="px-2 mb-2 text-xs font-semibold text-gray-400 uppercase tracking-wider">
            {searchQuery ? `Results (${sortedChatHistory.length})` : 'Recent'}
          </div>
        )}
        {/* Chat List */}
        {(isMobile || !sidebarCollapsed) && (
          <div className="flex-1 overflow-y-auto space-y-1 pr-1 custom-scrollbar">
            {sortedChatHistory.map(chat => (
              <div
                key={chat.id}
                onClick={() => { if (!isLoading) { setActiveChatId(chat.id); setIsNewChat(false); } }}
                className={`group relative w-full text-left px-3 py-2.5 rounded-lg flex items-center gap-3 transition-colors
                ${isLoading ? 'opacity-50 cursor-default' : 'cursor-pointer'}
                ${chat.id === activeChatId ? "bg-blue-50/80 text-blue-700" : "text-gray-600 hover:bg-gray-50"}
                ${sidebarCollapsed ? 'justify-center px-0' : ''}`}
                title={sidebarCollapsed ? (chat.title || "New Chat") : undefined}
              >
                <div className="relative flex-shrink-0">
                  <MessageSquareText size={18} className={`${chat.id === activeChatId ? "text-blue-600" : "text-gray-400"}`} />
                  {pinnedChats.includes(chat.id) && (
                    <Pin size={10} className="absolute -top-1 -right-1 text-amber-500 fill-amber-500" />
                  )}
                </div>

                {/* === TITLE & TIMESTAMP === */}
                {!sidebarCollapsed && (
                  <div className="flex-1 min-w-0">
                    <span className="truncate text-sm font-medium block max-w-[120px]">
                      {chat.title || "New Chat"}
                    </span>
                    {chat.updated_at && (
                      <span className="text-[10px] text-gray-400">
                        {formatTimeAgo(chat.updated_at)}
                      </span>
                    )}
                  </div>
                )}

                {/* === ACTION BUTTONS on Hover === */}
                {!sidebarCollapsed && (
                  <div className={`absolute right-2 flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity ${isLoading ? 'pointer-events-none opacity-0' : ''}`}>
                    <button
                      onClick={(e) => { e.currentTarget.blur(); togglePin(e, chat.id); }}
                      disabled={isLoading}
                      className={`p-1.5 rounded ${pinnedChats.includes(chat.id) ? 'text-amber-500' : 'text-gray-400 hover:text-amber-500 hover:bg-amber-50'}`}
                      title={pinnedChats.includes(chat.id) ? "Unpin" : "Pin"}
                    >
                      <Pin size={14} className={pinnedChats.includes(chat.id) ? 'fill-amber-500' : ''} />
                    </button>
                    <button
                      onClick={(e) => { e.currentTarget.blur(); handleDeleteSession(e, chat.id); }}
                      disabled={isLoading}
                      className="p-1.5 hover:bg-red-100 rounded text-gray-400 hover:text-red-500"
                      title="Delete"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* User Profile with Logout */}
        <div className={`mt-4 pt-4 border-t flex items-center gap-3 ${!isMobile && sidebarCollapsed ? 'justify-center flex-col' : ''}`}>
          <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 text-xs font-bold flex-shrink-0">
            {user.full_name ? user.full_name.charAt(0) : "U"}
          </div>
          {(isMobile || !sidebarCollapsed) && (
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-700 truncate">{user.full_name || user.name}</p>
            </div>
          )}
          <button
            onClick={(e) => { e.currentTarget.blur(); onLogout(); }}
            className={`flex items-center gap-1.5 text-gray-500 hover:text-red-600 hover:bg-red-50 px-2 py-1.5 rounded-lg transition-all text-sm font-medium ${!isMobile && sidebarCollapsed ? 'mt-2' : ''}`}
            title="Logout"
          >
            <LogOut size={16} />
            {(isMobile || !sidebarCollapsed) && <span>Logout</span>}
          </button>
        </div>
      </aside>

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
              <form
                onSubmit={handleSendMessage}
                className="space-y-2"
              >
                <div className="flex items-center justify-end gap-2 px-1">
                  <span className="text-[11px] font-medium text-gray-500">Answer mode</span>
                  <div className="inline-flex rounded-lg border border-gray-200 bg-white p-0.5">
                    <button
                      type="button"
                      onClick={(e) => { e.currentTarget.blur(); setUseVisionMode(false); }}
                      disabled={isLoading}
                      className={`px-2.5 py-1 text-[11px] font-semibold rounded-md transition-all ${!useVisionMode ? "bg-blue-600 text-white" : "text-gray-600 hover:bg-gray-100"} ${isLoading ? "opacity-60 cursor-default" : ""}`}
                    >
                      Text
                    </button>
                    <button
                      type="button"
                      onClick={(e) => { e.currentTarget.blur(); setUseVisionMode(true); }}
                      disabled={isLoading}
                      className={`px-2.5 py-1 text-[11px] font-semibold rounded-md transition-all ${useVisionMode ? "bg-blue-600 text-white" : "text-gray-600 hover:bg-gray-100"} ${isLoading ? "opacity-60 cursor-default" : ""}`}
                    >
                      Vision
                    </button>
                  </div>
                </div>
                <div className="flex-1 flex items-center bg-gray-50 border border-gray-200 rounded-3xl px-2 py-2 focus-within:ring-2 focus-within:ring-blue-100 transition-all focus-within:border-blue-300 focus-within:bg-white shadow-sm">
                  <input
                    ref={inputRef}
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder={isLoading ? "Press Enter to cancel the question" : isRecording ? "Listening... (Press Enter to stop)" : isTranscribing ? "Transcribing... (Press Enter to cancel)" : "Ask about PLC, automation... (Press Enter to enable voice input)"}
                    className="flex-1 bg-transparent focus:outline-none text-gray-800 placeholder-gray-400 px-3 py-1.5 min-w-0"
                    readOnly={isLoading || isTranscribing}
                    onKeyDown={handleInputKeyDown}
                    autoFocus
                    aria-label="Message input"
                  />
                  <button
                    type="button"
                    onClick={(e) => { e.currentTarget.blur(); (isTranscribing ? cancelTranscription : (isRecording ? stopRecording : startRecording))(); }}
                    disabled={isLoading}
                    className={`p-2.5 rounded-full transition-all flex-shrink-0 mr-1 group ${isLoading ? 'pointer-events-none opacity-50' : ''} ${isRecording
                      ? 'bg-blue-500 text-white animate-pulse'
                      : isTranscribing
                        ? 'bg-orange-100 text-orange-500 hover:bg-orange-200 cursor-pointer'
                        : 'hover:bg-gray-200 text-gray-500 hover:text-gray-700'
                      }`}
                    aria-label={isTranscribing ? "Cancel transcription" : (isRecording ? "Stop recording" : "Start voice input")}
                    title={isTranscribing ? "Click to cancel" : (isRecording ? "Click to stop" : "Voice input")}
                  >
                    {isTranscribing ? (
                      <div className="relative">
                        <LoaderCircle size={20} className="animate-spin" />
                        <X size={10} className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity" />
                      </div>
                    ) : isRecording ? (
                      <Ear size={20} />
                    ) : (
                      <Mic size={20} />
                    )}
                  </button>
                  {isLoading ? (
                    <button
                      type="button"
                      onClick={(e) => { e.currentTarget.blur(); abortControllerRef.current?.abort(); }}
                      className="bg-red-600 text-white p-2.5 rounded-full hover:bg-red-700 transition-all shadow-sm flex-shrink-0"
                      aria-label="Cancel request"
                      title="Cancel"
                    >
                      <StopCircle size={20} />
                    </button>
                  ) : (
                    <button
                      type="submit"
                      disabled={!input.trim() || isRecording || isTranscribing}
                      className="bg-blue-600 text-white p-2.5 rounded-full hover:bg-blue-700 disabled:bg-gray-200 disabled:text-gray-400 disabled:cursor-not-allowed transition-all shadow-sm flex-shrink-0"
                      aria-label="Send message"
                    >
                      <Send size={20} className={input.trim() ? "translate-x-0.5" : ""} />
                    </button>
                  )}
                </div>
              </form>
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
                  <div
                    key={i}
                    className={`flex flex-col ${m.sender === "user" ? "items-end" : "items-start"}`}
                  >
                    <div
                      className={`max-w-[85%] px-5 py-3.5 rounded-2xl shadow-sm text-[15px] leading-relaxed break-words overflow-hidden
                        ${m.sender === "user"
                          ? "bg-gradient-to-r from-blue-600 to-blue-500 text-white rounded-br-sm"
                          : "bg-white text-gray-800 border border-gray-100 rounded-bl-sm prose prose-sm max-w-none"
                        }`}
                      style={{ overflowWrap: 'anywhere', wordBreak: 'break-word' }}
                    >
                      {m.sender === "bot" ? (
                        m.isCancelled ? (
                          <span className="text-red-500 font-medium text-sm">{m.text}</span>
                        ) : m.isStreaming && !m.text ? (
                          <div className="flex items-center gap-3 text-gray-500 text-sm">
                            <LoaderCircle size={18} className="animate-spin text-blue-500" />
                            <span className="font-medium">Thinking...</span>
                          </div>
                        ) :
                          <ReactMarkdown
                            components={{
                              code({ inline, className, children, ...props }) {
                                const match = /language-(\w+)/.exec(className || '');
                                return !inline && match ? (
                                  <SyntaxHighlighter
                                    style={oneDark}
                                    language={match[1]}
                                    PreTag="div"
                                    className="rounded-lg text-sm my-2"
                                    {...props}
                                  >
                                    {String(children).replace(/\n$/, '')}
                                  </SyntaxHighlighter>
                                ) : (
                                  <code className="bg-gray-100 px-1.5 py-0.5 rounded text-sm font-mono" {...props}>
                                    {children}
                                  </code>
                                );
                              },
                              p({ children }) {
                                return <p className="mb-2 last:mb-0">{children}</p>;
                              },
                              ul({ children }) {
                                return <ul className="list-disc ml-4 mb-2">{children}</ul>;
                              },
                              ol({ children }) {
                                return <ol className="list-decimal ml-4 mb-2">{children}</ol>;
                              },
                              li({ children }) {
                                return <li className="mb-1">{children}</li>;
                              },
                              strong({ children }) {
                                return <strong className="font-semibold">{children}</strong>;
                              },
                              a({ href, children }) {
                                return <a href={href} className="text-blue-600 hover:underline" target="_blank" rel="noopener noreferrer">{children}</a>;
                              },
                              table({ children }) {
                                return (
                                  <div className="overflow-x-auto my-3">
                                    <table className="min-w-full border-collapse border border-gray-300 text-sm">
                                      {children}
                                    </table>
                                  </div>
                                );
                              },
                              thead({ children }) {
                                return <thead className="bg-gray-100">{children}</thead>;
                              },
                              tbody({ children }) {
                                return <tbody>{children}</tbody>;
                              },
                              tr({ children }) {
                                return <tr className="border-b border-gray-200">{children}</tr>;
                              },
                              th({ children }) {
                                return (
                                  <th className="border border-gray-300 px-3 py-2 text-left font-semibold bg-gray-50">
                                    {children}
                                  </th>
                                );
                              },
                              td({ children }) {
                                return (
                                  <td className="border border-gray-300 px-3 py-2">
                                    {children}
                                  </td>
                                );
                              },
                              hr() {
                                return null;
                              }
                            }}
                          >
                            {fixMarkdownTable(stripQualityMetrics(typeof m.text === 'string' ? m.text : String(m.text || '')))}
                          </ReactMarkdown>
                      ) : (
                        m.text
                      )}
                    </div>

                    {m.sender === "bot" && (
                      <div className="mt-1 max-w-[85%] rounded-xl border border-gray-200 bg-gray-50 px-3 py-2">
                        <div className="mb-1 flex items-center justify-between gap-2">
                          <div className="text-[10px] font-semibold uppercase tracking-wide text-gray-500">
                            RAGAS Metrics
                            {m.ragasStatus === "pending" ? " (Pending)" : ""}
                          </div>
                          {formatResponseMode(m.responseMode) && (
                            <span className="rounded bg-gray-200 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-gray-700">
                              Mode: {formatResponseMode(m.responseMode)}
                              {shouldShowVisionFallback(m) ? " (Fallback)" : ""}
                            </span>
                          )}
                        </div>
                        <div className="grid grid-cols-2 gap-x-3 gap-y-1">
                          {RAGAS_METRIC_KEYS.map((key) => (
                            <div
                              key={key}
                              className="flex items-center justify-between gap-2 text-[11px] text-gray-700"
                            >
                              <span>{RAGAS_METRIC_LABELS[key]}</span>
                              <span className="font-semibold text-gray-900">
                                {formatRagasMetric(m.ragas?.[key])}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    
                    <div className={`flex items-center gap-2 mt-1 ${m.sender === "user" ? "flex-row-reverse" : ""}`}>
                      {m.timestamp && (
                        <span className="text-[10px] text-gray-400 px-1">
                          {formatTime(m.timestamp)}
                        </span>
                      )}
                      <button
                        onClick={(e) => { e.currentTarget.blur(); copyToClipboard(stripQualityMetrics(m.text), i); }}
                        className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-all"
                        title={copiedMessageId === i ? "Copied!" : "Copy message"}
                      >
                        {copiedMessageId === i ? (
                          <Check size={14} className="text-green-500" />
                        ) : (
                          <Copy size={14} />
                        )}
                      </button>
                      <button
                        onClick={(e) => {
                          e.currentTarget.blur();
                          setInput(stripQualityMetrics(m.text));
                          inputRef.current?.focus();
                        }}
                        className="p-1 rounded hover:bg-blue-100 text-gray-400 hover:text-blue-600 transition-all"
                        title="Copy to chatbar"
                      >
                        <CornerDownLeft size={14} />
                      </button>
                    </div>
                  </div>
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
              <form
                onSubmit={handleSendMessage}
                className="max-w-3xl mx-auto space-y-2"
              >
                <div className="flex items-center justify-end gap-2 px-1">
                  <span className="text-[11px] font-medium text-gray-500">Answer mode</span>
                  <div className="inline-flex rounded-lg border border-gray-200 bg-white p-0.5">
                    <button
                      type="button"
                      onClick={(e) => { e.currentTarget.blur(); setUseVisionMode(false); }}
                      disabled={isLoading}
                      className={`px-2.5 py-1 text-[11px] font-semibold rounded-md transition-all ${!useVisionMode ? "bg-blue-600 text-white" : "text-gray-600 hover:bg-gray-100"} ${isLoading ? "opacity-60 cursor-default" : ""}`}
                    >
                      Text
                    </button>
                    <button
                      type="button"
                      onClick={(e) => { e.currentTarget.blur(); setUseVisionMode(true); }}
                      disabled={isLoading}
                      className={`px-2.5 py-1 text-[11px] font-semibold rounded-md transition-all ${useVisionMode ? "bg-blue-600 text-white" : "text-gray-600 hover:bg-gray-100"} ${isLoading ? "opacity-60 cursor-default" : ""}`}
                    >
                      Vision
                    </button>
                  </div>
                </div>
                <div className={`flex-1 flex items-center bg-gray-50 border border-gray-200 rounded-3xl px-2 py-2 focus-within:ring-2 focus-within:ring-blue-100 transition-all focus-within:border-blue-300 focus-within:bg-white shadow-sm ${isLoading ? 'opacity-60' : ''}`}>
                  <input
                    ref={inputRef}
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder={isLoading ? "Press Enter to cancel the question" : isRecording ? "Listening... (Press Enter to stop)" : isTranscribing ? "Transcribing... (Press Enter to cancel)" : "Ask about PLC, automation... (Press Enter to enable voice input)"}
                    className="flex-1 bg-transparent focus:outline-none text-gray-800 placeholder-gray-400 px-3 py-1.5"
                    readOnly={isLoading || isTranscribing}
                    onKeyDown={handleInputKeyDown}
                    autoFocus
                    aria-label="Message input"
                  />
                  <button
                    type="button"
                    onClick={(e) => { e.currentTarget.blur(); (isTranscribing ? cancelTranscription : (isRecording ? stopRecording : startRecording))(); }}
                    disabled={isLoading}
                    className={`p-2.5 rounded-full transition-all flex-shrink-0 mr-1 group ${isLoading ? 'pointer-events-none opacity-50' : ''} ${isRecording
                      ? 'bg-blue-500 text-white animate-pulse'
                      : isTranscribing
                        ? 'bg-orange-100 text-orange-500 hover:bg-orange-200 cursor-pointer'
                        : 'hover:bg-gray-200 text-gray-500 hover:text-gray-700'
                      }`}
                    aria-label={isTranscribing ? "Cancel transcription" : (isRecording ? "Stop recording" : "Start voice input")}
                    title={isTranscribing ? "Click to cancel" : (isRecording ? "Click to stop" : "Voice input")}
                  >
                    {isTranscribing ? (
                      <div className="relative">
                        <LoaderCircle size={20} className="animate-spin" />
                        <X size={10} className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity" />
                      </div>
                    ) : isRecording ? (
                      <Ear size={20} />
                    ) : (
                      <Mic size={20} />
                    )}
                  </button>
                  {isLoading ? (
                    <button
                      type="button"
                      onClick={(e) => { e.currentTarget.blur(); abortControllerRef.current?.abort(); }}
                      className="bg-red-600 text-white p-2.5 rounded-full hover:bg-red-700 transition-all shadow-sm flex-shrink-0"
                      aria-label="Cancel request"
                      title="Cancel"
                    >
                      <StopCircle size={20} />
                    </button>
                  ) : (
                    <button
                      type="submit"
                      disabled={!input.trim() || isRecording || isTranscribing}
                      className="bg-blue-600 text-white p-2.5 rounded-full hover:bg-blue-700 disabled:bg-gray-200 disabled:text-gray-400 disabled:cursor-not-allowed transition-all shadow-sm flex-shrink-0"
                      aria-label="Send message"
                    >
                      <Send size={20} className={input.trim() ? "translate-x-0.5" : ""} />
                    </button>
                  )}
                </div>
              </form>
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
