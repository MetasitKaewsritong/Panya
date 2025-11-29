// App.jsx v2.3 - with Chat History Support
// ✅ CHANGES:
// 1. ส่ง chat history ไป backend
// 2. แสดง mode ตามที่ user เลือก (auto/fast/deep)
// 3. Deep mode แสดงเป็น "🔍 Deep" (ไม่ใช่ "Deep Think")

import { useState, useEffect, useRef } from "react";
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
  Brain,
  ChevronDown,
} from "lucide-react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { CopyToClipboard } from "react-copy-to-clipboard";

// --- Helper: คำนวณเวลาที่ผ่านไป ---
const timeAgo = (date) => {
  const seconds = Math.floor((new Date() - new Date(date)) / 1000);
  let interval = seconds / 31536000;
  if (interval > 1) return Math.floor(interval) + " years ago";
  interval = seconds / 2592000;
  if (interval > 1) return Math.floor(interval) + " months ago";
  interval = seconds / 86400;
  if (interval > 1) return Math.floor(interval) + " days ago";
  interval = seconds / 3600;
  if (interval > 1) return Math.floor(interval) + " hours ago";
  interval = seconds / 60;
  if (interval > 1) return Math.floor(interval) + " minutes ago";
  return "Just now";
};

// ⚡ Helper: ตรวจสอบประเภทไฟล์
const getFileType = (file) => {
  if (!file) return null;
  const mimeType = file.type;
  if (mimeType.startsWith("image/")) return "image";
  if (mimeType.startsWith("audio/")) return "audio";
  if (mimeType === "application/pdf") return "pdf";
  if (mimeType === "text/plain" || file.name.endsWith(".txt")) return "text";
  if (mimeType === "text/csv" || file.name.endsWith(".csv")) return "csv";
  if (mimeType === "application/json" || file.name.endsWith(".json")) return "json";
  if (file.name.endsWith(".docx") || file.name.endsWith(".doc")) return "document";
  return "unknown";
};

// ⚡ Helper: แสดง icon ตามประเภทไฟล์
const FilePreviewIcon = ({ fileType, className }) => {
  switch (fileType) {
    case "image":
      return <ImageIcon className={className} />;
    case "audio":
      return <FileAudio className={className} />;
    case "pdf":
    case "text":
    case "csv":
    case "json":
    case "document":
      return <FileText className={className} />;
    default:
      return <FileText className={className} />;
  }
};

// ✅ UPDATED: Mode Selector Component
const ModeSelector = ({ mode, setMode, disabled }) => {
  const [isOpen, setIsOpen] = useState(false);
  
  const modes = [
    { id: "auto", label: "Auto", icon: Brain, description: "เลือกอัตโนมัติตามสถานการณ์", color: "text-purple-600" },
    { id: "fast", label: "Fast", icon: Zap, description: "เร็ว ~5-10 วินาที", color: "text-yellow-600" },
    { id: "deep", label: "Deep", icon: Gauge, description: "ละเอียด ~30-60 วินาที", color: "text-blue-600" },
  ];
  
  const currentMode = modes.find(m => m.id === mode) || modes[0];
  const CurrentIcon = currentMode.icon;
  
  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => !disabled && setIsOpen(!isOpen)}
        disabled={disabled}
        className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border transition-all text-sm font-medium
          ${disabled ? 'opacity-50 cursor-not-allowed bg-gray-100' : 'hover:bg-gray-50 cursor-pointer'}
          ${currentMode.color} border-gray-300`}
      >
        <CurrentIcon size={16} />
        <span>{currentMode.label}</span>
        <ChevronDown size={14} className={`transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>
      
      {isOpen && !disabled && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setIsOpen(false)} />
          <div className="absolute bottom-full left-0 mb-2 w-64 bg-white rounded-xl shadow-lg border border-gray-200 overflow-hidden z-20">
            <div className="p-2 border-b bg-gray-50">
              <p className="text-xs text-gray-500 font-medium">เลือกโหมดการตอบ</p>
            </div>
            {modes.map((m) => {
              const Icon = m.icon;
              return (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => {
                    setMode(m.id);
                    setIsOpen(false);
                  }}
                  className={`w-full flex items-start gap-3 p-3 hover:bg-gray-50 transition-colors text-left
                    ${mode === m.id ? 'bg-blue-50' : ''}`}
                >
                  <Icon size={20} className={m.color} />
                  <div>
                    <p className={`font-medium ${m.color}`}>{m.label}</p>
                    <p className="text-xs text-gray-500">{m.description}</p>
                  </div>
                  {mode === m.id && (
                    <Check size={16} className="ml-auto text-blue-600" />
                  )}
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
};

const CodeBlock = ({ language, value }) => {
  const [isCopied, setIsCopied] = useState(false);
  const handleCopy = () => {
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  };
  return (
    <div className="relative my-2 text-sm font-mono">
      <div className="flex items-center justify-between bg-gray-800 text-gray-300 px-4 py-1.5 rounded-t-md">
        <span className="text-xs">{language || "code"}</span>
        <CopyToClipboard text={value} onCopy={handleCopy}>
          <button className="flex items-center gap-1.5 text-xs hover:text-white transition-colors">
            {isCopied ? (
              <Check size={14} className="text-green-500" />
            ) : (
              <Copy size={14} />
            )}
            {isCopied ? "Copied!" : "Copy code"}
          </button>
        </CopyToClipboard>
      </div>
      <SyntaxHighlighter
        language={language}
        style={oneDark}
        customStyle={{
          margin: 0,
          borderRadius: "0 0 0.375rem 0.375rem",
          padding: "1rem",
        }}
      >
        {String(value ?? "").trim()}
      </SyntaxHighlighter>
    </div>
  );
};

const MessageContent = ({ text }) => {
  const safeText = String(text ?? "");
  const codeBlockRegex = /```(\w+)?\n([\s\S]+?)\n```/g;
  const parts = safeText.split(codeBlockRegex);

  return (
    <div>
      {parts.map((part, index) => {
        if (index % 3 === 2) {
          const language = parts[index - 1] || "plaintext";
          return <CodeBlock key={index} language={language} value={part} />;
        } else if (index % 3 === 0) {
          return (
            <p key={index} className="whitespace-pre-wrap">
              {part}
            </p>
          );
        }
        return null;
      })}
    </div>
  );
};

// ✅ UPDATED: Message component with proper mode display
const Message = ({ text, sender, image, fileName, fileType, mode }) => {
  const isUser = sender === "user";
  
  // ✅ Helper function to get mode display
  const getModeDisplay = (modeValue) => {
    if (!modeValue) return null;
    
    switch(modeValue.toLowerCase()) {
      case 'auto':
        return { label: '🤖 Auto', bgClass: 'bg-purple-100 text-purple-700' };
      case 'fast':
        return { label: '⚡ Fast', bgClass: 'bg-yellow-100 text-yellow-700' };
      case 'deep':
        return { label: '🔍 Deep', bgClass: 'bg-blue-100 text-blue-700' };
      default:
        return { label: modeValue, bgClass: 'bg-gray-100 text-gray-700' };
    }
  };
  
  const modeDisplay = getModeDisplay(mode);
  
  return (
    <div className={`flex items-start gap-3 ${isUser ? "justify-end" : ""} my-4`}>
      {!isUser && (
        <div className="flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center bg-gray-700 text-white">
          <Bot size={20} />
        </div>
      )}
      <div className={`max-w-2xl px-5 py-3 rounded-xl shadow-sm break-words ${isUser ? "bg-blue-600 text-white" : "bg-white text-gray-800 border"}`}>
        {/* ✅ แสดง mode badge */}
        {modeDisplay && !isUser && (
          <div className="flex items-center gap-1 mb-2">
            <span className={`text-xs px-2 py-0.5 rounded-full ${modeDisplay.bgClass}`}>
              {modeDisplay.label}
            </span>
          </div>
        )}
        {/* แสดง preview ตามประเภทไฟล์ */}
        {image && fileType === "image" && (
          <img src={image} alt="upload" className="mb-2 max-h-40 rounded border" />
        )}
        {fileName && fileType !== "image" && (
          <div className="mb-2 flex items-center gap-2 p-2 bg-gray-100 rounded border">
            <FilePreviewIcon fileType={fileType} className="w-6 h-6 text-blue-500" />
            <span className="text-sm text-gray-700 truncate">{fileName}</span>
          </div>
        )}
        <MessageContent text={text} />
      </div>
      {isUser && (
        <div className="flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center bg-blue-600 text-white">
          <User size={20} />
        </div>
      )}
    </div>
  );
};

// ------------- Voice Modal -------------------
const VoiceRecorderModal = ({ isOpen, onClose, onTranscriptionComplete }) => {
  const [status, setStatus] = useState("idle");
  const [timer, setTimer] = useState(0);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const timerIntervalRef = useRef(null);
  const streamRef = useRef(null);

  useEffect(() => {
    if (isOpen) {
      setStatus("idle");
      setTimer(0);
      audioChunksRef.current = [];
    } else {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
        streamRef.current = null;
      }
    }
  }, [isOpen]);

  useEffect(() => {
    if (status === "recording") {
      timerIntervalRef.current = setInterval(() => setTimer(prev => prev + 1), 1000);
    } else {
      clearInterval(timerIntervalRef.current);
      if (status !== "idle") setTimer(0);
    }
    return () => clearInterval(timerIntervalRef.current);
  }, [status]);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      mediaRecorderRef.current = new MediaRecorder(stream);
      audioChunksRef.current = [];
      mediaRecorderRef.current.ondataavailable = (event) => audioChunksRef.current.push(event.data);
      mediaRecorderRef.current.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        onTranscriptionComplete(audioBlob);
        stream.getTracks().forEach(track => track.stop());
        streamRef.current = null;
        setStatus('transcribing');
      };
      mediaRecorderRef.current.start();
      setStatus('recording');
    } catch (err) {
      alert("Could not access microphone. Please check your browser permissions.");
      onClose();
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
    const minutes = Math.floor(seconds / 60).toString().padStart(2, '0');
    const secs = (seconds % 60).toString().padStart(2, '0');
    return `${minutes}:${secs}`;
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl shadow-xl p-8 text-center w-full max-w-md">
        <h2 className="text-2xl font-bold mb-4">Voice Input</h2>
        <p className="text-gray-500 mb-6">
          {status === 'idle' && 'Click the button to start recording.'}
          {status === 'recording' && 'Recording... Click to stop.'}
          {status === 'transcribing' && 'Processing your audio...'}
        </p>
        <div className="text-5xl font-mono mb-6">{formatTime(timer)}</div>
        <button
          onClick={() => status === 'recording' ? stopRecording() : startRecording()}
          disabled={status === 'transcribing'}
          className={`w-20 h-20 rounded-full transition-all duration-300 flex items-center justify-center mx-auto shadow-lg ${status === 'recording' ? 'bg-red-500 hover:bg-red-600' : 'bg-blue-500 hover:bg-blue-600'} disabled:bg-gray-400 disabled:cursor-wait`}
        >
          {status === 'transcribing' ? <LoaderCircle size={32} className="text-white animate-spin" /> : <Mic size={32} className="text-white" />}
        </button>
        <button onClick={handleCancel} className="text-sm text-gray-500 hover:text-gray-800 mt-6" disabled={status === 'transcribing'}>Cancel</button>
      </div>
    </div>
  );
};

// ------------- Main App -------------------
function App() {
  const [chatHistory, setChatHistory] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null); 
  const [selectedFile, setSelectedFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [fileType, setFileType] = useState(null);
  
  const [fileMode, setFileMode] = useState("auto");
  
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isUploading, setIsUploading] = useState(false);

  const [isVoiceModalOpen, setIsVoiceModalOpen] = useState(false);

  const chatEndRef = useRef(null);
  const fileInputRef = useRef(null);

  const API_URL = import.meta.env.VITE_API_URL || "http://localhost:5000";

  const ACCEPTED_FILE_TYPES = [
    "image/*",
    "audio/*",
    ".pdf",
    ".txt",
    ".csv",
    ".json",
    ".doc,.docx",
  ].join(",");

  useEffect(() => {
    try {
      const savedHistory = localStorage.getItem("plcnextChatHistory");
      const thirtyDaysAgo = Date.now() - 30 * 24 * 60 * 60 * 1000;
      let history = savedHistory ? JSON.parse(savedHistory) : [];
      const recentHistory = history.filter(
        (chat) => new Date(chat.createdAt).getTime() > thirtyDaysAgo
      );
      setChatHistory(recentHistory);
      if (recentHistory.length > 0) {
        setActiveChatId(recentHistory[0].id);
      } else {
        handleNewChat();
      }
    } catch (error) {
      handleNewChat();
    }
  }, []);

  useEffect(() => {
    if (chatHistory.length > 0) {
      localStorage.setItem("plcnextChatHistory", JSON.stringify(chatHistory));
    }
  }, [chatHistory]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatHistory, activeChatId]);

  const handleTranscriptionComplete = async (audioBlob) => {
    const formData = new FormData();
    formData.append('file', audioBlob, 'recording.webm');
    try {
      const res = await axios.post(`${API_URL}/api/transcribe`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setInput((prev) => (prev ? prev + ' ' : '') + (res.data.text || ""));
    } catch (err) {
      alert("ถอดเสียงไม่สำเร็จ: " + err.message);
    } finally {
      setIsVoiceModalOpen(false);
    }
  };

  const handleNewChat = () => {
    const newChat = {
      id: Date.now().toString(),
      title: "New Chat",
      createdAt: new Date().toISOString(),
      messages: [
        {
          text: "Hello! I am Panya, your AI assistant for PLCnext. How can I help you today?",
          sender: "bot",
        },
      ],
    };
    setChatHistory((prev) => [newChat, ...prev]);
    setActiveChatId(newChat.id);
    setInput("");
  };

  const handleSelectChat = (chatId) => {
    setActiveChatId(chatId);
  };

  const handleDeleteChat = (e, chatIdToDelete) => {
    e.stopPropagation();
    setConfirmDeleteId(chatIdToDelete);
  };
  
  const confirmDeleteChat = () => {
    setChatHistory((prev) =>
      prev.filter((chat) => chat.id !== confirmDeleteId)
    );
    if (activeChatId === confirmDeleteId) {
      const remainingChats = chatHistory.filter(
        (chat) => chat.id !== confirmDeleteId
      );
      if (remainingChats.length > 0) {
        setActiveChatId(remainingChats[0].id);
      } else {
        handleNewChat();
      }
    }
    setConfirmDeleteId(null);
  };
  
  const cancelDeleteChat = () => {
    setConfirmDeleteId(null);
  };

  const handleFileSelect = (event) => {
    const file = event.target.files[0];
    if (!file) return;
    
    const detectedType = getFileType(file);
    setSelectedFile(file);
    setFileType(detectedType);
    
    if (detectedType === "image") {
      setPreviewUrl(URL.createObjectURL(file));
    } else {
      setPreviewUrl(null);
    }
    
    event.target.value = null;
  };

  const cancelFileSelection = () => {
    setSelectedFile(null);
    setPreviewUrl(null);
    setFileType(null);
  };

  // ✅ UPDATED: Send Message with chat history
  const handleSendMessage = async (e) => {
    e.preventDefault();
    const userText = input.trim();
    if ((!userText && !selectedFile) || isLoading || isUploading || !activeChatId) return;

    const userMessage = {
      text: userText,
      sender: "user",
      image: fileType === "image" ? previewUrl : null,
      fileName: selectedFile?.name || null,
      fileType: fileType,
    };
    setInput("");
    setIsLoading(true);

    // Get current chat's messages for history
    const activeChat = chatHistory.find(chat => chat.id === activeChatId);
    const currentMessages = activeChat ? activeChat.messages : [];

    // Push user message
    setChatHistory((prev) => {
      const newHistory = [...prev];
      const activeChatIndex = newHistory.findIndex(
        (chat) => chat.id === activeChatId
      );
      if (activeChatIndex !== -1) {
        newHistory[activeChatIndex].messages.push(userMessage);
        const userMessages = newHistory[activeChatIndex].messages.filter(
          (m) => m.sender === "user"
        );
        if (userMessages.length === 1) {
          newHistory[activeChatIndex].title =
            userText.length > 30 ? `${userText.substring(0, 27)}...` : (userText || selectedFile?.name || "File upload");
        }
      }
      return newHistory;
    });

    try {
      const formData = new FormData();
      formData.append("message", userText);
      formData.append("mode", fileMode);
      
      // ✅ NEW: ส่ง chat history ไป backend
      const historyForBackend = currentMessages.map(msg => ({
        text: msg.text,
        sender: msg.sender
      }));
      formData.append("chat_history", JSON.stringify(historyForBackend));
      
      if (selectedFile) {
        formData.append("file", selectedFile);
      }
      
      const response = await axios.post(
        `${API_URL}/api/agent-chat`,
        formData,
        { 
          headers: { "Content-Type": "multipart/form-data" },
          onUploadProgress: (progressEvent) => {
            const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            setUploadProgress(percentCompleted);
            if (percentCompleted < 100) {
              setIsUploading(true);
            } else {
              setIsUploading(false);
            }
          }
        }
      );

      const botMessage = { 
        text: (response.data.reply ?? response.data.answer ?? ""), 
        sender: "bot",
        mode: response.data.mode || null
      };

      setChatHistory((prev) => {
        const newHistory = [...prev];
        const activeChatIndex = newHistory.findIndex(
          (chat) => chat.id === activeChatId
        );
        if (activeChatIndex !== -1) {
          newHistory[activeChatIndex].messages.push(botMessage);
        }
        return newHistory;
      });
    } catch (error) {
      const errorMessageText =
        error.response?.data?.detail ||
        "Sorry, there was an error connecting to the server.";
      const errorMessage = { text: errorMessageText, sender: "bot" };
      setChatHistory((prev) => {
        const newHistory = [...prev];
        const activeChatIndex = newHistory.findIndex(
          (chat) => chat.id === activeChatId
        );
        if (activeChatIndex !== -1) {
          newHistory[activeChatIndex].messages.push(errorMessage);
        }
        return newHistory;
      });
    } finally {
      setIsLoading(false);
      setIsUploading(false);
      setUploadProgress(0);
      setSelectedFile(null);
      setPreviewUrl(null);
      setFileType(null);
    }
  };

  const activeChat = chatHistory.find((chat) => chat.id === activeChatId);
  const messagesToDisplay = activeChat ? activeChat.messages : [];

  return (
    <>
      <VoiceRecorderModal
        isOpen={isVoiceModalOpen}
        onClose={() => setIsVoiceModalOpen(false)}
        onTranscriptionComplete={handleTranscriptionComplete}
      />
      <div className="flex h-screen bg-white text-gray-800 font-sans">
        {/* Sidebar */}
        <aside
          className={`bg-gray-50 border-r border-gray-200 flex flex-col transition-all duration-300 ease-in-out ${
            isSidebarOpen ? "w-72 p-4" : "w-0 p-0"
          }`}
        >
          <div
            className={`flex-shrink-0 mb-4 flex items-center justify-between overflow-hidden transition-opacity duration-200 ${
              isSidebarOpen ? "opacity-100" : "opacity-0"
            }`}
          >
            <div className="flex items-center gap-3">
              <div className="bg-blue-600 p-1 rounded-full">
                <img
                  src="/src/assets/logo.png"
                  alt="PLCnext Logo"
                  className="w-10 h-10 object-cover rounded-full border-2 border-white shadow"
                />
              </div>
              <h1 className="text-xl font-bold text-gray-900">Panya</h1>
            </div>
          </div>

          <button
            className={`flex items-center justify-center gap-2 w-full p-2.5 mb-4 bg-blue-600 text-white hover:bg-blue-700 rounded-lg transition-colors text-sm font-semibold mx-auto overflow-hidden ${
              isSidebarOpen ? "opacity-100" : "opacity-0"
            }`}
            onClick={handleNewChat}
          >
            <Plus size={18} /> New Chat
          </button>

          {/* Chat History List */}
          <div
            className={`flex-1 overflow-y-auto space-y-2 transition-opacity duration-200 ${
              isSidebarOpen ? "opacity-100" : "opacity-0"
            }`}
          >
            {chatHistory.map((chat) => (
              <div
                key={chat.id}
                onClick={() => handleSelectChat(chat.id)}
                className={`group relative flex items-center justify-between w-full p-2.5 rounded-lg cursor-pointer transition-colors ${
                  activeChatId === chat.id
                    ? "bg-blue-100 text-blue-800"
                    : "hover:bg-gray-200"
                }`}
              >
                <div className="flex items-center gap-3">
                  <MessageSquareText size={16} className="text-gray-500" />
                  <div className="flex flex-col">
                    <span className="text-sm font-medium truncate w-40">
                      {chat.title}
                    </span>
                    <span className="text-xs text-gray-400">
                      {timeAgo(chat.createdAt)}
                    </span>
                  </div>
                </div>
                <button
                  onClick={(e) => handleDeleteChat(e, chat.id)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </div>
          
          {/* Delete Confirmation Modal */}
          {confirmDeleteId && (
            <div className="fixed inset-0 z-40 bg-black bg-opacity-40 flex items-center justify-center">
              <div className="bg-white rounded-lg shadow-xl p-6 w-80 flex flex-col items-center">
                <p className="text-lg font-semibold text-gray-800 mb-4 text-center">
                  คุณต้องการลบแชทนี้หรือไม่?
                </p>
                <div className="flex gap-4">
                  <button
                    className="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded"
                    onClick={confirmDeleteChat}
                  >
                    ใช่, ลบ
                  </button>
                  <button
                    className="bg-gray-200 hover:bg-gray-300 text-gray-800 px-4 py-2 rounded"
                    onClick={cancelDeleteChat}
                  >
                    ไม่ลบ
                  </button>
                </div>
              </div>
            </div>
          )}
        </aside>
        
        {/* Main Content */}
        <div className="flex-1 flex flex-col bg-gray-100">
          <header className="flex items-center p-2 bg-white border-b border-gray-200 shadow-sm">
            <button
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              className="p-2 text-gray-500 hover:text-gray-900 hover:bg-gray-100 rounded-md transition-colors"
            >
              <PanelLeft size={20} />
            </button>
            <h2 className="ml-2 font-semibold text-gray-700">
              {activeChat?.title || "Smart Assistant"}
            </h2>
          </header>

          <main className="flex-1 p-6 overflow-y-auto">
            <div className="max-w-4xl mx-auto">
              {messagesToDisplay.map((msg, index) => (
                <Message 
                  key={index} 
                  text={msg.text} 
                  sender={msg.sender} 
                  image={msg.image}
                  fileName={msg.fileName}
                  fileType={msg.fileType}
                  mode={msg.mode}
                />
              ))}
              {isLoading && (
                <div className="flex items-start gap-3 my-4">
                  <div className="flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center bg-gray-700 text-white">
                    <Bot size={20} />
                  </div>
                  <div className="max-w-lg px-5 py-4 rounded-xl shadow-sm bg-white border">
                    <div className="flex items-center space-x-2">
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-pulse [animation-delay:-0.3s]"></div>
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-pulse [animation-delay:-0.15s]"></div>
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-pulse"></div>
                    </div>
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>
          </main>
          
          {/* Footer/INPUT bar */}
          <footer className="p-4 bg-gray-100/80 backdrop-blur-sm">
            <div className="max-w-4xl mx-auto">
              <div className={`bg-white border border-gray-300 shadow-sm focus-within:ring-2 focus-within:ring-blue-400 rounded-2xl`}>
                <form onSubmit={handleSendMessage} className="p-2">
                  {/* Preview + Progress Bar */}
                  {selectedFile && (
                    <div className="relative m-2 p-2 border rounded-lg bg-gray-50 inline-flex items-center gap-2">
                      {fileType === "image" && previewUrl ? (
                        <img src={previewUrl} alt="Preview" className="w-24 h-24 object-contain rounded-md" />
                      ) : (
                        <div className="flex items-center gap-2 px-2">
                          <FilePreviewIcon fileType={fileType} className="w-8 h-8 text-blue-500" />
                          <div className="flex flex-col">
                            <span className="text-sm text-gray-700 max-w-[150px] truncate">{selectedFile.name}</span>
                            <span className="text-xs text-gray-400">
                              {(selectedFile.size / 1024).toFixed(1)} KB
                            </span>
                          </div>
                        </div>
                      )}
                      {isUploading && (
                        <div className="absolute bottom-0 left-0 right-0 h-1 bg-gray-200 rounded-b-lg overflow-hidden">
                          <div 
                            className="h-full bg-blue-500 transition-all duration-300"
                            style={{ width: `${uploadProgress}%` }}
                          />
                        </div>
                      )}
                      {isUploading && (
                        <span className="text-xs text-blue-600 font-medium">{uploadProgress}%</span>
                      )}
                      <button 
                        onClick={cancelFileSelection} 
                        className="absolute -top-2 -right-2 bg-gray-600 text-white rounded-full p-0.5 hover:bg-red-500 transition-colors" 
                        type="button"
                        disabled={isUploading}
                      >
                        <XCircle size={20} />
                      </button>
                    </div>
                  )}
                  <div className="flex items-center space-x-2">
                    <input 
                      type="file" 
                      ref={fileInputRef} 
                      onChange={handleFileSelect} 
                      className="hidden" 
                      accept={ACCEPTED_FILE_TYPES} 
                    />
                    {/* Mode Selector */}
                    <ModeSelector mode={fileMode} setMode={setFileMode} disabled={isLoading} />
                    <button type="button" onClick={() => fileInputRef.current.click()} className="p-2 text-gray-500 hover:text-blue-600 hover:bg-gray-100 rounded-full transition-colors disabled:opacity-50 disabled:cursor-not-allowed" aria-label="Attach file" disabled={isLoading}><Paperclip size={20} /></button>
                    <button type="button" onClick={() => setIsVoiceModalOpen(true)} className="p-2 text-gray-500 hover:text-blue-600 hover:bg-gray-100 rounded-full transition-colors disabled:opacity-50 disabled:cursor-not-allowed" aria-label="Use microphone" disabled={isLoading}><Mic size={20} /></button>
                    <input
                      type="text"
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      placeholder="Ask something about PLCnext..."
                      className="flex-1 bg-transparent focus:outline-none px-2 text-gray-800 placeholder-gray-500"
                      disabled={isLoading}
                    />
                    <button type="submit" className="bg-blue-600 text-white p-2.5 rounded-full font-semibold hover:bg-blue-700 shadow-sm disabled:bg-blue-300 disabled:cursor-not-allowed flex-shrink-0" disabled={isLoading || isUploading || (!input.trim() && !selectedFile)} aria-label="Send message">
                      {isUploading ? <LoaderCircle size={20} className="animate-spin" /> : <Send size={20} />}
                    </button>
                  </div>
                </form>
              </div>
              <p className="text-xs text-gray-400 text-center mt-2">
                Supported: Images, Audio, PDF, TXT, CSV, JSON, DOC/DOCX
              </p>
            </div>
          </footer>
        </div>
      </div>
    </>
  );
}

export default App;