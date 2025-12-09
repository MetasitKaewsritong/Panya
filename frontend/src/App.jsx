// ============================================================================
// App.jsx v3.0 - Universal PLC Assistant
// ============================================================================
// CHANGES FROM ORIGINAL:
// 1. ✅ Removed Auto mode - only Fast and Deep modes available
// 2. ✅ Generic PLC branding (removed all PLCnext references)
// 3. ✅ Improved code organization and comments
// 4. ✅ Better error handling
// 5. ✅ Performance optimizations (useCallback, useMemo)
// 6. ✅ Accessibility improvements
// 7. ✅ Better UX with loading states and feedback
//
// MODE EXPLANATION:
// - FAST MODE: Direct LLM response without RAG. Best for:
//   * General questions about PLC concepts
//   * Quick troubleshooting tips
//   * Programming syntax help
//   * When you need fast answers (~5-15 seconds)
//
// - DEEP MODE: Uses RAG (Retrieval-Augmented Generation). Best for:
//   * Specific documentation lookups
//   * Detailed technical specifications
//   * When accuracy from docs is critical (~30-60 seconds)
//   * Questions about specific products/models in your knowledge base
// ============================================================================

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import axios from "axios";
import {
  Send,
  Bot,
  User,
  Copy,
  Check,
  PanelLeft,
  Plus,
  MessageSquareText,
  Trash2,
  Paperclip,
  Mic,
  XCircle,
  LoaderCircle,
  FileText,
  FileAudio,
  Image as ImageIcon,
  Zap,
  Gauge,
  ChevronDown,
  AlertCircle,
} from "lucide-react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { CopyToClipboard } from "react-copy-to-clipboard";

// ============================================================================
// CONFIGURATION
// ============================================================================
const CONFIG = {
  API_URL: import.meta.env.VITE_API_URL || "http://localhost:5000",
  STORAGE_KEY: "plcAssistantChatHistory",
  MAX_HISTORY_DAYS: 30,
  MAX_CHAT_HISTORY_FOR_CONTEXT: 10,
  ACCEPTED_FILE_TYPES: [
    "image/*",
    "audio/*",
    ".pdf",
    ".txt",
    ".csv",
    ".json",
    ".doc,.docx",
  ].join(","),
};

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Calculate human-readable time ago string
 */
const timeAgo = (date) => {
  const seconds = Math.floor((new Date() - new Date(date)) / 1000);
  
  const intervals = [
    { label: "year", seconds: 31536000 },
    { label: "month", seconds: 2592000 },
    { label: "day", seconds: 86400 },
    { label: "hour", seconds: 3600 },
    { label: "minute", seconds: 60 },
  ];
  
  for (const interval of intervals) {
    const count = Math.floor(seconds / interval.seconds);
    if (count >= 1) {
      return `${count} ${interval.label}${count > 1 ? "s" : ""} ago`;
    }
  }
  return "Just now";
};

/**
 * Detect file type from File object
 */
const getFileType = (file) => {
  if (!file) return null;
  
  const mimeType = file.type;
  const fileName = file.name.toLowerCase();
  
  if (mimeType.startsWith("image/")) return "image";
  if (mimeType.startsWith("audio/")) return "audio";
  if (mimeType === "application/pdf" || fileName.endsWith(".pdf")) return "pdf";
  if (mimeType === "text/plain" || fileName.endsWith(".txt")) return "text";
  if (mimeType === "text/csv" || fileName.endsWith(".csv")) return "csv";
  if (mimeType === "application/json" || fileName.endsWith(".json")) return "json";
  if (fileName.endsWith(".docx") || fileName.endsWith(".doc")) return "document";
  
  return "unknown";
};

/**
 * Format file size for display
 */
const formatFileSize = (bytes) => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

// ============================================================================
// COMPONENTS
// ============================================================================

/**
 * File type icon component
 */
const FilePreviewIcon = ({ fileType, className }) => {
  const icons = {
    image: ImageIcon,
    audio: FileAudio,
    pdf: FileText,
    text: FileText,
    csv: FileText,
    json: FileText,
    document: FileText,
  };
  
  const Icon = icons[fileType] || FileText;
  return <Icon className={className} />;
};

/**
 * Mode Selector Component
 * Allows switching between Fast and Deep modes
 */
const ModeSelector = ({ mode, setMode, disabled }) => {
  const [isOpen, setIsOpen] = useState(false);
  
  const modes = useMemo(() => [
    { 
      id: "fast", 
      label: "Fast", 
      icon: Zap, 
      description: "Quick LLM response for general questions", 
      timing: "~5-15s",
      color: "text-yellow-600",
      bgColor: "bg-yellow-50",
      borderColor: "border-yellow-200"
    },
    { 
      id: "deep", 
      label: "Deep", 
      icon: Gauge, 
      description: "RAG search through documentation", 
      timing: "~30-60s",
      color: "text-blue-600",
      bgColor: "bg-blue-50",
      borderColor: "border-blue-200"
    },
  ], []);
  
  const currentMode = modes.find(m => m.id === mode) || modes[0];
  const CurrentIcon = currentMode.icon;
  
  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = () => setIsOpen(false);
    if (isOpen) {
      document.addEventListener("click", handleClickOutside);
      return () => document.removeEventListener("click", handleClickOutside);
    }
  }, [isOpen]);
  
  return (
    <div className="relative">
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          if (!disabled) setIsOpen(!isOpen);
        }}
        disabled={disabled}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border transition-all text-sm font-medium
          ${disabled ? 'opacity-50 cursor-not-allowed bg-gray-100' : 'hover:bg-gray-50 cursor-pointer'}
          ${currentMode.color} ${currentMode.borderColor}`}
        aria-label={`Current mode: ${currentMode.label}. Click to change.`}
        aria-expanded={isOpen}
      >
        <CurrentIcon size={16} />
        <span>{currentMode.label}</span>
        <ChevronDown 
          size={14} 
          className={`transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`} 
        />
      </button>
      
      {isOpen && !disabled && (
        <div 
          className="absolute bottom-full left-0 mb-2 w-72 bg-white rounded-xl shadow-xl border border-gray-200 overflow-hidden z-20"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="p-3 border-b bg-gray-50">
            <p className="text-sm font-semibold text-gray-700">Select Response Mode</p>
            <p className="text-xs text-gray-500 mt-1">Choose based on your needs</p>
          </div>
          {modes.map((m) => {
            const Icon = m.icon;
            const isSelected = mode === m.id;
            return (
              <button
                key={m.id}
                type="button"
                onClick={() => {
                  setMode(m.id);
                  setIsOpen(false);
                }}
                className={`w-full flex items-start gap-3 p-3 hover:bg-gray-50 transition-colors text-left
                  ${isSelected ? m.bgColor : ''}`}
              >
                <div className={`p-2 rounded-lg ${m.bgColor}`}>
                  <Icon size={20} className={m.color} />
                </div>
                <div className="flex-1">
                  <div className="flex items-center justify-between">
                    <p className={`font-semibold ${m.color}`}>{m.label}</p>
                    <span className="text-xs text-gray-400">{m.timing}</span>
                  </div>
                  <p className="text-xs text-gray-500 mt-0.5">{m.description}</p>
                </div>
                {isSelected && (
                  <Check size={16} className="text-green-500 mt-1" />
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};

/**
 * Code Block Component with syntax highlighting
 */
const CodeBlock = ({ language, value }) => {
  const [isCopied, setIsCopied] = useState(false);
  
  const handleCopy = useCallback(() => {
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  }, []);
  
  return (
    <div className="relative my-3 text-sm font-mono rounded-lg overflow-hidden">
      <div className="flex items-center justify-between bg-gray-800 text-gray-300 px-4 py-2">
        <span className="text-xs font-medium uppercase tracking-wide">
          {language || "code"}
        </span>
        <CopyToClipboard text={value} onCopy={handleCopy}>
          <button 
            className="flex items-center gap-1.5 text-xs hover:text-white transition-colors px-2 py-1 rounded hover:bg-gray-700"
            aria-label="Copy code"
          >
            {isCopied ? (
              <>
                <Check size={14} className="text-green-400" />
                <span className="text-green-400">Copied!</span>
              </>
            ) : (
              <>
                <Copy size={14} />
                <span>Copy</span>
              </>
            )}
          </button>
        </CopyToClipboard>
      </div>
      <SyntaxHighlighter
        language={language}
        style={oneDark}
        customStyle={{
          margin: 0,
          borderRadius: 0,
          padding: "1rem",
        }}
      >
        {String(value ?? "").trim()}
      </SyntaxHighlighter>
    </div>
  );
};

/**
 * Message Content Parser - handles code blocks and text
 */
const MessageContent = ({ text }) => {
  const safeText = String(text ?? "");
  
  // Parse code blocks with regex
  const parts = useMemo(() => {
    const codeBlockRegex = /```(\w+)?\n([\s\S]+?)\n```/g;
    const result = [];
    let lastIndex = 0;
    let match;
    
    while ((match = codeBlockRegex.exec(safeText)) !== null) {
      // Add text before code block
      if (match.index > lastIndex) {
        result.push({
          type: "text",
          content: safeText.slice(lastIndex, match.index)
        });
      }
      // Add code block
      result.push({
        type: "code",
        language: match[1] || "plaintext",
        content: match[2]
      });
      lastIndex = match.index + match[0].length;
    }
    
    // Add remaining text
    if (lastIndex < safeText.length) {
      result.push({
        type: "text",
        content: safeText.slice(lastIndex)
      });
    }
    
    return result;
  }, [safeText]);
  
  return (
    <div className="message-content">
      {parts.map((part, index) => {
        if (part.type === "code") {
          return <CodeBlock key={index} language={part.language} value={part.content} />;
        }
        return (
          <p key={index} className="whitespace-pre-wrap leading-relaxed">
            {part.content}
          </p>
        );
      })}
    </div>
  );
};

/**
 * Chat Message Component
 */
const Message = ({ text, sender, image, fileName, fileType, mode, isError }) => {
  const isUser = sender === "user";
  
  const getModeDisplay = useCallback((modeValue) => {
    if (!modeValue) return null;
    
    const modeConfig = {
      fast: { label: '⚡ Fast', bgClass: 'bg-yellow-100 text-yellow-700' },
      deep: { label: '🔍 Deep', bgClass: 'bg-blue-100 text-blue-700' },
    };
    
    return modeConfig[modeValue.toLowerCase()] || { 
      label: modeValue, 
      bgClass: 'bg-gray-100 text-gray-700' 
    };
  }, []);
  
  const modeDisplay = getModeDisplay(mode);
  
  return (
    <div 
      className={`flex items-start gap-3 ${isUser ? "justify-end" : ""} my-4 animate-fadeIn`}
      role="listitem"
    >
      {!isUser && (
        <div className="flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center bg-gradient-to-br from-gray-700 to-gray-800 text-white shadow-md">
          <Bot size={20} />
        </div>
      )}
      <div 
        className={`max-w-2xl px-5 py-3 rounded-2xl shadow-sm break-words
          ${isUser 
            ? "bg-gradient-to-br from-blue-500 to-blue-600 text-white" 
            : isError 
              ? "bg-red-50 text-red-800 border border-red-200"
              : "bg-white text-gray-800 border border-gray-100"
          }`}
      >
        {/* Mode badge */}
        {modeDisplay && !isUser && (
          <div className="flex items-center gap-2 mb-2">
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${modeDisplay.bgClass}`}>
              {modeDisplay.label}
            </span>
          </div>
        )}
        
        {/* Error icon */}
        {isError && (
          <div className="flex items-center gap-2 mb-2 text-red-600">
            <AlertCircle size={16} />
            <span className="text-xs font-medium">Error</span>
          </div>
        )}
        
        {/* Image preview */}
        {image && fileType === "image" && (
          <img 
            src={image} 
            alt="Uploaded content" 
            className="mb-3 max-h-48 rounded-lg border border-gray-200 shadow-sm" 
          />
        )}
        
        {/* File attachment display */}
        {fileName && fileType !== "image" && (
          <div className="mb-3 flex items-center gap-2 p-2 bg-gray-50 rounded-lg border border-gray-200">
            <FilePreviewIcon fileType={fileType} className="w-5 h-5 text-blue-500" />
            <span className="text-sm text-gray-700 truncate">{fileName}</span>
          </div>
        )}
        
        <MessageContent text={text} />
      </div>
      
      {isUser && (
        <div className="flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center bg-gradient-to-br from-blue-500 to-blue-600 text-white shadow-md">
          <User size={20} />
        </div>
      )}
    </div>
  );
};

/**
 * Loading indicator for bot responses
 */
const LoadingMessage = () => (
  <div className="flex items-start gap-3 my-4 animate-fadeIn">
    <div className="flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center bg-gradient-to-br from-gray-700 to-gray-800 text-white shadow-md">
      <Bot size={20} />
    </div>
    <div className="max-w-lg px-5 py-4 rounded-2xl shadow-sm bg-white border border-gray-100">
      <div className="flex items-center space-x-2">
        <div className="w-2.5 h-2.5 bg-blue-400 rounded-full animate-bounce [animation-delay:-0.3s]"></div>
        <div className="w-2.5 h-2.5 bg-blue-400 rounded-full animate-bounce [animation-delay:-0.15s]"></div>
        <div className="w-2.5 h-2.5 bg-blue-400 rounded-full animate-bounce"></div>
        <span className="text-sm text-gray-400 ml-2">Thinking...</span>
      </div>
    </div>
  </div>
);

/**
 * Voice Recorder Modal Component
 */
const VoiceRecorderModal = ({ isOpen, onClose, onTranscriptionComplete, apiUrl }) => {
  const [status, setStatus] = useState("idle");
  const [timer, setTimer] = useState(0);
  const [error, setError] = useState(null);
  
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const timerIntervalRef = useRef(null);
  const streamRef = useRef(null);

  // Reset state when modal opens/closes
  useEffect(() => {
    if (isOpen) {
      setStatus("idle");
      setTimer(0);
      setError(null);
      audioChunksRef.current = [];
    } else {
      // Cleanup on close
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
        streamRef.current = null;
      }
      clearInterval(timerIntervalRef.current);
    }
  }, [isOpen]);

  // Timer management
  useEffect(() => {
    if (status === "recording") {
      timerIntervalRef.current = setInterval(() => setTimer(prev => prev + 1), 1000);
    } else {
      clearInterval(timerIntervalRef.current);
    }
    return () => clearInterval(timerIntervalRef.current);
  }, [status]);

  const startRecording = async () => {
    try {
      setError(null);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      
      mediaRecorderRef.current = new MediaRecorder(stream);
      audioChunksRef.current = [];
      
      mediaRecorderRef.current.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };
      
      mediaRecorderRef.current.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        stream.getTracks().forEach(track => track.stop());
        streamRef.current = null;
        setStatus('transcribing');
        
        // Send for transcription
        try {
          const formData = new FormData();
          formData.append('file', audioBlob, 'recording.webm');
          const res = await axios.post(`${apiUrl}/api/transcribe`, formData, {
            headers: { "Content-Type": "multipart/form-data" },
          });
          onTranscriptionComplete(res.data.text || "");
          onClose();
        } catch (err) {
          setError("Transcription failed: " + (err.response?.data?.detail || err.message));
          setStatus("idle");
        }
      };
      
      mediaRecorderRef.current.start();
      setStatus('recording');
    } catch (err) {
      setError("Could not access microphone. Please check your browser permissions.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.stop();
    }
  };
  
  const handleCancel = () => {
    if (mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.onstop = null;
      mediaRecorderRef.current.stop();
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
    onClose(); 
  };

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60).toString().padStart(2, '0');
    const secs = (seconds % 60).toString().padStart(2, '0');
    return `${mins}:${secs}`;
  };

  if (!isOpen) return null;

  return (
    <div 
      className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50"
      role="dialog"
      aria-modal="true"
      aria-labelledby="voice-modal-title"
    >
      <div className="bg-white rounded-2xl shadow-2xl p-8 text-center w-full max-w-md mx-4">
        <h2 id="voice-modal-title" className="text-2xl font-bold mb-2">Voice Input</h2>
        <p className="text-gray-500 mb-6">
          {status === 'idle' && 'Click the microphone to start recording'}
          {status === 'recording' && 'Recording... Click to stop'}
          {status === 'transcribing' && 'Processing your audio...'}
        </p>
        
        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            {error}
          </div>
        )}
        
        <div className="text-5xl font-mono mb-6 text-gray-700">{formatTime(timer)}</div>
        
        <button
          onClick={() => status === 'recording' ? stopRecording() : startRecording()}
          disabled={status === 'transcribing'}
          className={`w-24 h-24 rounded-full transition-all duration-300 flex items-center justify-center mx-auto shadow-lg
            ${status === 'recording' 
              ? 'bg-red-500 hover:bg-red-600 animate-pulse' 
              : 'bg-blue-500 hover:bg-blue-600'
            } 
            disabled:bg-gray-400 disabled:cursor-wait`}
          aria-label={status === 'recording' ? 'Stop recording' : 'Start recording'}
        >
          {status === 'transcribing' 
            ? <LoaderCircle size={36} className="text-white animate-spin" /> 
            : <Mic size={36} className="text-white" />
          }
        </button>
        
        <button 
          onClick={handleCancel} 
          className="text-sm text-gray-500 hover:text-gray-800 mt-6 px-4 py-2 rounded-lg hover:bg-gray-100 transition-colors" 
          disabled={status === 'transcribing'}
        >
          Cancel
        </button>
      </div>
    </div>
  );
};

/**
 * Delete Confirmation Modal
 */
const DeleteConfirmModal = ({ isOpen, onConfirm, onCancel }) => {
  if (!isOpen) return null;
  
  return (
    <div 
      className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center"
      role="dialog"
      aria-modal="true"
    >
      <div className="bg-white rounded-xl shadow-2xl p-6 w-80 mx-4">
        <h3 className="text-lg font-semibold text-gray-800 mb-2">Delete Chat?</h3>
        <p className="text-sm text-gray-500 mb-4">This action cannot be undone.</p>
        <div className="flex gap-3">
          <button
            className="flex-1 bg-red-500 hover:bg-red-600 text-white px-4 py-2 rounded-lg font-medium transition-colors"
            onClick={onConfirm}
          >
            Delete
          </button>
          <button
            className="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 px-4 py-2 rounded-lg font-medium transition-colors"
            onClick={onCancel}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
};

/**
 * File Preview Component in input area
 */
const FilePreview = ({ file, fileType, previewUrl, isUploading, uploadProgress, onCancel }) => (
  <div className="relative m-2 p-3 border rounded-xl bg-gray-50 inline-flex items-center gap-3">
    {fileType === "image" && previewUrl ? (
      <img src={previewUrl} alt="Preview" className="w-20 h-20 object-cover rounded-lg" />
    ) : (
      <div className="flex items-center gap-3">
        <div className="p-2 bg-blue-100 rounded-lg">
          <FilePreviewIcon fileType={fileType} className="w-6 h-6 text-blue-600" />
        </div>
        <div className="flex flex-col">
          <span className="text-sm font-medium text-gray-700 max-w-[150px] truncate">
            {file.name}
          </span>
          <span className="text-xs text-gray-400">
            {formatFileSize(file.size)}
          </span>
        </div>
      </div>
    )}
    
    {/* Upload progress bar */}
    {isUploading && (
      <>
        <div className="absolute bottom-0 left-0 right-0 h-1 bg-gray-200 rounded-b-xl overflow-hidden">
          <div 
            className="h-full bg-blue-500 transition-all duration-300"
            style={{ width: `${uploadProgress}%` }}
          />
        </div>
        <span className="text-xs text-blue-600 font-medium">{uploadProgress}%</span>
      </>
    )}
    
    {/* Remove button */}
    <button 
      onClick={onCancel} 
      className="absolute -top-2 -right-2 bg-gray-600 text-white rounded-full p-1 hover:bg-red-500 transition-colors shadow-md" 
      type="button"
      disabled={isUploading}
      aria-label="Remove file"
    >
      <XCircle size={18} />
    </button>
  </div>
);

// ============================================================================
// MAIN APP COMPONENT
// ============================================================================
function App() {
  // State management
  const [chatHistory, setChatHistory] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [selectedFile, setSelectedFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [fileType, setFileType] = useState(null);
  const [fileMode, setFileMode] = useState("fast"); // Default to Fast mode
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const [isVoiceModalOpen, setIsVoiceModalOpen] = useState(false);

  // Refs
  const chatEndRef = useRef(null);
  const fileInputRef = useRef(null);
  const inputRef = useRef(null);

  // Load chat history from localStorage on mount
  useEffect(() => {
    try {
      const savedHistory = localStorage.getItem(CONFIG.STORAGE_KEY);
      if (savedHistory) {
        const history = JSON.parse(savedHistory);
        const cutoffDate = Date.now() - CONFIG.MAX_HISTORY_DAYS * 24 * 60 * 60 * 1000;
        const recentHistory = history.filter(
          (chat) => new Date(chat.createdAt).getTime() > cutoffDate
        );
        setChatHistory(recentHistory);
        if (recentHistory.length > 0) {
          setActiveChatId(recentHistory[0].id);
        } else {
          handleNewChat();
        }
      } else {
        handleNewChat();
      }
    } catch (error) {
      console.error("Error loading chat history:", error);
      handleNewChat();
    }
  }, []);

  // Save chat history to localStorage when it changes
  useEffect(() => {
    if (chatHistory.length > 0) {
      try {
        localStorage.setItem(CONFIG.STORAGE_KEY, JSON.stringify(chatHistory));
      } catch (error) {
        console.error("Error saving chat history:", error);
      }
    }
  }, [chatHistory]);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatHistory, activeChatId]);

  // Keyboard shortcut for sending (Ctrl+Enter)
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.ctrlKey && e.key === 'Enter' && !isLoading) {
        handleSendMessage(e);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [input, isLoading, selectedFile]);

  // Handlers
  const handleNewChat = useCallback(() => {
    const newChat = {
      id: Date.now().toString(),
      title: "New Chat",
      createdAt: new Date().toISOString(),
      messages: [
        {
          text: "Hello! I'm your PLC & Industrial Automation Assistant. I can help you with:\n\n• PLC programming (Ladder, ST, FBD, etc.)\n• Troubleshooting industrial equipment\n• Communication protocols (Modbus, PROFINET, etc.)\n• Technical documentation\n\nHow can I assist you today?",
          sender: "bot",
        },
      ],
    };
    setChatHistory((prev) => [newChat, ...prev]);
    setActiveChatId(newChat.id);
    setInput("");
    inputRef.current?.focus();
  }, []);

  const handleSelectChat = useCallback((chatId) => {
    setActiveChatId(chatId);
  }, []);

  const handleDeleteChat = useCallback((e, chatIdToDelete) => {
    e.stopPropagation();
    setConfirmDeleteId(chatIdToDelete);
  }, []);
  
  const confirmDeleteChat = useCallback(() => {
    setChatHistory((prev) => {
      const filtered = prev.filter((chat) => chat.id !== confirmDeleteId);
      if (activeChatId === confirmDeleteId) {
        if (filtered.length > 0) {
          setActiveChatId(filtered[0].id);
        } else {
          // Will trigger new chat creation
          setTimeout(handleNewChat, 0);
        }
      }
      return filtered;
    });
    setConfirmDeleteId(null);
  }, [confirmDeleteId, activeChatId, handleNewChat]);

  const handleTranscriptionComplete = useCallback((text) => {
    if (text) {
      setInput((prev) => (prev ? prev + ' ' : '') + text);
      inputRef.current?.focus();
    }
  }, []);

  const handleFileSelect = useCallback((event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    
    const detectedType = getFileType(file);
    setSelectedFile(file);
    setFileType(detectedType);
    
    if (detectedType === "image") {
      setPreviewUrl(URL.createObjectURL(file));
    } else {
      setPreviewUrl(null);
    }
    
    // Reset input to allow selecting same file again
    event.target.value = "";
  }, []);

  const cancelFileSelection = useCallback(() => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }
    setSelectedFile(null);
    setPreviewUrl(null);
    setFileType(null);
  }, [previewUrl]);

  const handleSendMessage = useCallback(async (e) => {
    e?.preventDefault();
    
    const userText = input.trim();
    if ((!userText && !selectedFile) || isLoading || isUploading || !activeChatId) return;

    const userMessage = {
      text: userText,
      sender: "user",
      image: fileType === "image" ? previewUrl : null,
      fileName: selectedFile?.name || null,
      fileType: fileType,
    };
    
    // Clear input immediately for better UX
    setInput("");
    setIsLoading(true);

    // Get current messages for context
    const activeChat = chatHistory.find(chat => chat.id === activeChatId);
    const currentMessages = activeChat?.messages || [];

    // Add user message to chat
    setChatHistory((prev) => {
      const newHistory = [...prev];
      const idx = newHistory.findIndex((chat) => chat.id === activeChatId);
      if (idx !== -1) {
        newHistory[idx] = {
          ...newHistory[idx],
          messages: [...newHistory[idx].messages, userMessage],
          // Update title on first user message
          title: newHistory[idx].messages.filter(m => m.sender === "user").length === 0
            ? (userText.length > 30 ? `${userText.substring(0, 27)}...` : (userText || selectedFile?.name || "File upload"))
            : newHistory[idx].title
        };
      }
      return newHistory;
    });

    try {
      const formData = new FormData();
      formData.append("message", userText);
      formData.append("mode", fileMode);
      
      // Send chat history for context
      const historyForBackend = currentMessages
        .slice(-CONFIG.MAX_CHAT_HISTORY_FOR_CONTEXT)
        .map(msg => ({
          text: msg.text,
          sender: msg.sender
        }));
      formData.append("chat_history", JSON.stringify(historyForBackend));
      
      if (selectedFile) {
        formData.append("file", selectedFile);
      }
      
      const response = await axios.post(
        `${CONFIG.API_URL}/api/agent-chat`,
        formData,
        { 
          headers: { "Content-Type": "multipart/form-data" },
          timeout: 180000, // 3 minute timeout for deep mode
          onUploadProgress: (progressEvent) => {
            const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            setUploadProgress(percent);
            setIsUploading(percent < 100);
          }
        }
      );

      const botMessage = { 
        text: response.data.reply ?? response.data.answer ?? "I received your message but couldn't generate a response.",
        sender: "bot",
        mode: response.data.mode || fileMode
      };

      setChatHistory((prev) => {
        const newHistory = [...prev];
        const idx = newHistory.findIndex((chat) => chat.id === activeChatId);
        if (idx !== -1) {
          newHistory[idx] = {
            ...newHistory[idx],
            messages: [...newHistory[idx].messages, botMessage]
          };
        }
        return newHistory;
      });
    } catch (error) {
      console.error("API Error:", error);
      const errorMessage = { 
        text: error.response?.data?.detail || error.message || "Sorry, there was an error connecting to the server. Please try again.",
        sender: "bot",
        isError: true
      };
      
      setChatHistory((prev) => {
        const newHistory = [...prev];
        const idx = newHistory.findIndex((chat) => chat.id === activeChatId);
        if (idx !== -1) {
          newHistory[idx] = {
            ...newHistory[idx],
            messages: [...newHistory[idx].messages, errorMessage]
          };
        }
        return newHistory;
      });
    } finally {
      setIsLoading(false);
      setIsUploading(false);
      setUploadProgress(0);
      cancelFileSelection();
    }
  }, [input, selectedFile, fileType, previewUrl, isLoading, isUploading, activeChatId, chatHistory, fileMode, cancelFileSelection]);

  // Derived state
  const activeChat = useMemo(
    () => chatHistory.find((chat) => chat.id === activeChatId),
    [chatHistory, activeChatId]
  );
  const messagesToDisplay = activeChat?.messages || [];

  // ============================================================================
  // RENDER
  // ============================================================================
  return (
    <>
      {/* Voice Recording Modal */}
      <VoiceRecorderModal
        isOpen={isVoiceModalOpen}
        onClose={() => setIsVoiceModalOpen(false)}
        onTranscriptionComplete={handleTranscriptionComplete}
        apiUrl={CONFIG.API_URL}
      />
      
      {/* Delete Confirmation Modal */}
      <DeleteConfirmModal
        isOpen={!!confirmDeleteId}
        onConfirm={confirmDeleteChat}
        onCancel={() => setConfirmDeleteId(null)}
      />
      
      <div className="flex h-screen bg-gray-50 text-gray-800 font-sans">
        {/* ================================================================ */}
        {/* SIDEBAR */}
        {/* ================================================================ */}
        <aside
          className={`bg-white border-r border-gray-200 flex flex-col transition-all duration-300 ease-in-out shadow-sm
            ${isSidebarOpen ? "w-72" : "w-0"}`}
        >
          <div className={`flex flex-col h-full ${isSidebarOpen ? "p-4" : "p-0 overflow-hidden"}`}>
            {/* Logo/Brand */}
            <div className="flex-shrink-0 mb-4 flex items-center gap-3">
              <div className="bg-gradient-to-br from-blue-500 to-blue-600 p-2 rounded-xl shadow-md">
                <Bot className="w-7 h-7 text-white" />
              </div>
              <div>
                <h1 className="text-lg font-bold text-gray-900">PLC Assistant</h1>
                <p className="text-xs text-gray-500">Industrial Automation AI</p>
              </div>
            </div>

            {/* New Chat Button */}
            <button
              className="flex items-center justify-center gap-2 w-full p-3 mb-4 bg-gradient-to-r from-blue-500 to-blue-600 text-white hover:from-blue-600 hover:to-blue-700 rounded-xl transition-all text-sm font-semibold shadow-md hover:shadow-lg"
              onClick={handleNewChat}
            >
              <Plus size={18} /> New Chat
            </button>

            {/* Chat History List */}
            <div className="flex-1 overflow-y-auto space-y-1" role="list" aria-label="Chat history">
              {chatHistory.map((chat) => (
                <div
                  key={chat.id}
                  onClick={() => handleSelectChat(chat.id)}
                  className={`group relative flex items-center w-full p-3 rounded-xl cursor-pointer transition-all
                    ${activeChatId === chat.id
                      ? "bg-blue-50 text-blue-700 shadow-sm"
                      : "hover:bg-gray-50"
                    }`}
                  role="listitem"
                  aria-selected={activeChatId === chat.id}
                >
                  <MessageSquareText size={16} className="text-gray-400 mr-3 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{chat.title}</p>
                    <p className="text-xs text-gray-400">{timeAgo(chat.createdAt)}</p>
                  </div>
                  <button
                    onClick={(e) => handleDeleteChat(e, chat.id)}
                    className="absolute right-2 p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg opacity-0 group-hover:opacity-100 transition-all"
                    aria-label="Delete chat"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
            
            {/* Mode Info */}
            <div className="mt-4 p-3 bg-gray-50 rounded-xl text-xs text-gray-500">
              <p className="font-medium text-gray-700 mb-1">Mode Tips:</p>
              <p><strong>⚡ Fast:</strong> General questions</p>
              <p><strong>🔍 Deep:</strong> Documentation search</p>
            </div>
          </div>
        </aside>
        
        {/* ================================================================ */}
        {/* MAIN CONTENT */}
        {/* ================================================================ */}
        <div className="flex-1 flex flex-col bg-gray-50">
          {/* Header */}
          <header className="flex items-center gap-2 px-4 py-3 bg-white border-b border-gray-200 shadow-sm">
            <button
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              className="p-2 text-gray-500 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
              aria-label={isSidebarOpen ? "Close sidebar" : "Open sidebar"}
            >
              <PanelLeft size={20} />
            </button>
            <h2 className="font-semibold text-gray-700 truncate">
              {activeChat?.title || "PLC Assistant"}
            </h2>
          </header>

          {/* Messages Area */}
          <main className="flex-1 overflow-y-auto p-6" role="log" aria-live="polite">
            <div className="max-w-4xl mx-auto">
              {messagesToDisplay.map((msg, index) => (
                <Message 
                  key={`${activeChatId}-${index}`}
                  text={msg.text} 
                  sender={msg.sender} 
                  image={msg.image}
                  fileName={msg.fileName}
                  fileType={msg.fileType}
                  mode={msg.mode}
                  isError={msg.isError}
                />
              ))}
              {isLoading && <LoadingMessage />}
              <div ref={chatEndRef} />
            </div>
          </main>
          
          {/* ================================================================ */}
          {/* INPUT AREA */}
          {/* ================================================================ */}
          <footer className="p-4 bg-gray-50 border-t border-gray-100">
            <div className="max-w-4xl mx-auto">
              <div className="bg-white border border-gray-200 shadow-sm focus-within:ring-2 focus-within:ring-blue-400 focus-within:border-blue-400 rounded-2xl transition-all">
                <form onSubmit={handleSendMessage} className="p-2">
                  {/* File Preview */}
                  {selectedFile && (
                    <FilePreview
                      file={selectedFile}
                      fileType={fileType}
                      previewUrl={previewUrl}
                      isUploading={isUploading}
                      uploadProgress={uploadProgress}
                      onCancel={cancelFileSelection}
                    />
                  )}
                  
                  {/* Input Controls */}
                  <div className="flex items-center gap-2">
                    <input 
                      type="file" 
                      ref={fileInputRef} 
                      onChange={handleFileSelect} 
                      className="hidden" 
                      accept={CONFIG.ACCEPTED_FILE_TYPES}
                      aria-hidden="true"
                    />
                    
                    {/* Mode Selector */}
                    <ModeSelector mode={fileMode} setMode={setFileMode} disabled={isLoading} />
                    
                    {/* File Attach Button */}
                    <button 
                      type="button" 
                      onClick={() => fileInputRef.current?.click()} 
                      className="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed" 
                      aria-label="Attach file" 
                      disabled={isLoading}
                    >
                      <Paperclip size={20} />
                    </button>
                    
                    {/* Voice Button */}
                    <button 
                      type="button" 
                      onClick={() => setIsVoiceModalOpen(true)} 
                      className="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed" 
                      aria-label="Voice input" 
                      disabled={isLoading}
                    >
                      <Mic size={20} />
                    </button>
                    
                    {/* Text Input */}
                    <input
                      ref={inputRef}
                      type="text"
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      placeholder="Ask about PLC, automation, troubleshooting..."
                      className="flex-1 bg-transparent focus:outline-none px-3 py-2 text-gray-800 placeholder-gray-400"
                      disabled={isLoading}
                      aria-label="Message input"
                    />
                    
                    {/* Send Button */}
                    <button 
                      type="submit" 
                      className="bg-gradient-to-r from-blue-500 to-blue-600 text-white p-2.5 rounded-xl font-semibold hover:from-blue-600 hover:to-blue-700 shadow-md hover:shadow-lg disabled:from-gray-300 disabled:to-gray-400 disabled:cursor-not-allowed disabled:shadow-none transition-all flex-shrink-0" 
                      disabled={isLoading || isUploading || (!input.trim() && !selectedFile)} 
                      aria-label="Send message"
                    >
                      {isUploading ? (
                        <LoaderCircle size={20} className="animate-spin" />
                      ) : (
                        <Send size={20} />
                      )}
                    </button>
                  </div>
                </form>
              </div>
              
              {/* Helper Text */}
              <p className="text-xs text-gray-400 text-center mt-2">
                Supports: Images, Audio, PDF, TXT, CSV, JSON, DOCX
              </p>
            </div>
          </footer>
        </div>
      </div>
      
      {/* Global Styles */}
      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .animate-fadeIn {
          animation: fadeIn 0.3s ease-out;
        }
      `}</style>
    </>
  );
}

export default App;