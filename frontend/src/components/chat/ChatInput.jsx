import React from 'react';
import { LoaderCircle, X, Ear, Mic, StopCircle, Send } from 'lucide-react';

export default function ChatInput({
  handleSendMessage,
  setAnswerMode,
  isLoading,
  useVisionMode,
  inputRef,
  input,
  setInput,
  isRecording,
  isTranscribing,
  handleInputKeyDown,
  cancelTranscription,
  stopRecording,
  startRecording,
  abortControllerRef
}) {
  return (
    <form
      onSubmit={handleSendMessage}
      className="w-full space-y-2"
    >
      <div className="flex items-center justify-end gap-2 px-1">
        <span className="text-[11px] font-medium text-gray-500">Answer mode</span>
        <div className="inline-flex rounded-lg border border-gray-200 bg-white p-0.5">
          <button
            type="button"
            onClick={(e) => { e.currentTarget.blur(); setAnswerMode("text"); }}
            disabled={isLoading}
            className={`px-2.5 py-1 text-[11px] font-semibold rounded-md transition-all ${!useVisionMode ? "bg-blue-600 text-white" : "text-gray-600 hover:bg-gray-100"} ${isLoading ? "opacity-60 cursor-default" : ""}`}
          >
            Text
          </button>
          <button
            type="button"
            onClick={(e) => { e.currentTarget.blur(); setAnswerMode("vision"); }}
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
  );
}
