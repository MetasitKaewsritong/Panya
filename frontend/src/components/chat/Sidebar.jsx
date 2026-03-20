import React from 'react';
import { Bot, PanelLeft, PanelLeftClose, Plus, Search, X, MessageSquareText, Pin, Trash2, LogOut } from 'lucide-react';
import { formatTimeAgo } from '../../utils/formatters';

export default function Sidebar({
  isMobile,
  sidebarCollapsed,
  setSidebarCollapsed,
  isLoading,
  handleNewChat,
  searchQuery,
  setSearchQuery,
  sortedChatHistory,
  activeChatId,
  setActiveChatId,
  setIsNewChat,
  pinnedChats,
  togglePin,
  handleDeleteSession,
  user,
  onLogout
}) {
  return (
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
  );
}
