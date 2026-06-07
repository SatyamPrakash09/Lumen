import { useState, useEffect, useRef } from 'react';
import { api, streamAgentResponse } from '../api';
import Sidebar from './Sidebar';
import ChatArea from './ChatArea';
import MessageInput from './MessageInput';
import DragDropOverlay from './DragDropOverlay';

export default function Dashboard({ user, onLogout }) {
  const [sessions, setSessions] = useState([]);
  const [activeSession, setActiveSession] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [messages, setMessages] = useState([]);
  const [query, setQuery] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [thinkingSteps, setThinkingSteps] = useState([]);
  const [dragActive, setDragActive] = useState(false);

  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);

  // Load user sessions on mount
  useEffect(() => {
    loadSessions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Fetch session history & documents when active session changes
  useEffect(() => {
    if (activeSession) {
      loadSessionData(activeSession.session_id);
    } else {
      setMessages([]);
      setDocuments([]);
    }
  }, [activeSession]);

  // Document polling cycle: runs if any document is processing or pending
  useEffect(() => {
    if (!activeSession) return;

    const hasUnfinishedDocs = documents.some(
      (doc) => doc.status === 'pending' || doc.status === 'processing'
    );

    if (hasUnfinishedDocs) {
      const interval = setInterval(async () => {
        try {
          const docs = await api.listDocuments(activeSession.session_id);
          
          // Check if any previously pending/processing document is now missing
          const missingDocs = documents.filter(
            prevDoc => (prevDoc.status === 'pending' || prevDoc.status === 'processing') && 
                       !docs.some(d => d.id === prevDoc.id)
          );
          
          if (missingDocs.length > 0) {
            const names = missingDocs.map(d => d.file_name).join(', ');
            alert(`Upload failed: The file(s) "${names}" could not be processed and have been removed.`);
          }

          setDocuments(docs);
        } catch (e) {
          console.error('Failed to poll documents:', e);
        }
      }, 3000);

      return () => clearInterval(interval);
    }
  }, [documents, activeSession]);

  // Scroll to bottom when messages list changes or streaming is active
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isStreaming, thinkingSteps]);

  const loadSessions = async () => {
    try {
      const list = await api.listSessions();
      setSessions(list);
      if (list.length > 0 && !activeSession) {
        setActiveSession(list[0]);
      }
    } catch (e) {
      console.error('Failed to load sessions:', e);
    }
  };

  const loadSessionData = async (sessionId) => {
    try {
      const docs = await api.listDocuments(sessionId);
      setDocuments(docs);
      const history = await api.getMessages(sessionId);
      
      // Format history
      const formatted = history.map(msg => ({
        id: msg.id,
        sender: msg.sender === 'user' ? 'user' : 'ai',
        content: msg.content,
        citations: msg.citations,
        sources: msg.sources,
        tools_used: msg.tools_used,
        timestamp: msg.timestamp
      }));
      setMessages(formatted);
    } catch (e) {
      console.error('Failed to load session details:', e);
    }
  };

  const handleCreateSession = async (title) => {
    try {
      const session = await api.createSession(title);
      setSessions(prev => [session, ...prev]);
      setActiveSession(session);
    } catch (e) {
      console.error('Failed to create session:', e);
    }
  };

  const handleDeleteSession = async (sessionId, e) => {
    e.stopPropagation();
    if (!window.confirm('Delete this session and all its documents?')) return;
    try {
      await api.deleteSession(sessionId);
      setSessions(prev => prev.filter(s => s.session_id !== sessionId));
      if (activeSession?.session_id === sessionId) {
        setActiveSession(null);
      }
    } catch (e) {
      console.error('Failed to delete session:', e);
    }
  };

  const handleFileUpload = async (files) => {
    if (!activeSession || files.length === 0) return;

    const allowedExtensions = ['pdf', 'docx', 'txt', 'md', 'csv'];
    const validFiles = Array.from(files).filter(file => {
      const ext = file.name.split('.').pop().toLowerCase();
      return allowedExtensions.includes(ext);
    });

    if (validFiles.length === 0) {
      alert(`Upload failed: File type not allowed. Allowed: ${allowedExtensions.join(', ')}`);
      return;
    }

    setIsUploading(true);
    try {
      const uploaded = await api.uploadDocuments(activeSession.session_id, validFiles);
      setDocuments(prev => [...prev, ...uploaded]);
    } catch (e) {
      alert(`Upload failed: ${e.message}`);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileUpload(e.dataTransfer.files);
    }
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!query.trim() || !activeSession || isStreaming) return;

    const userQuery = query;
    setQuery('');

    // Optimistically add user query to messages
    const optimUserMsg = {
      id: 'temp-user-' + Date.now(),
      sender: 'user',
      content: userQuery,
      timestamp: new Date().toISOString()
    };
    setMessages(prev => [...prev, optimUserMsg]);

    setIsStreaming(true);
    setThinkingSteps([]);

    // Create temporary AI message placeholder
    const aiMsgId = 'temp-ai-' + Date.now();
    const optimAiMsg = {
      id: aiMsgId,
      sender: 'ai',
      content: '',
      citations: [],
      sources: [],
      tools_used: [],
      timestamp: new Date().toISOString()
    };
    setMessages(prev => [...prev, optimAiMsg]);

    let accumulatedContent = '';

    try {
      const stream = streamAgentResponse(activeSession.session_id, userQuery);
      
      for await (const chunk of stream) {
        if (chunk.type === 'token') {
          accumulatedContent += chunk.content;
          setMessages(prev =>
            prev.map(m => m.id === aiMsgId ? { ...m, content: accumulatedContent } : m)
          );
        } else if (chunk.type === 'tool_start') {
          setThinkingSteps(prev => {
            const exists = prev.some(s => s.tool === chunk.tool);
            if (exists) return prev;
            
            let descriptiveName = chunk.tool;
            if (chunk.tool === 'search_documents') descriptiveName = 'Searching local knowledge base...';
            else if (chunk.tool === 'web_search') descriptiveName = 'Verifying with DuckDuckGo web search...';
            else if (chunk.tool === 'wikipedia_search') descriptiveName = 'Fetching Wikipedia definitions...';
            else if (chunk.tool === 'calculator') descriptiveName = 'Computing mathematical formula...';
            else if (chunk.tool === 'get_current_datetime') descriptiveName = 'Checking current date & time...';
            
            return [...prev, {
              tool: chunk.tool,
              input: chunk.input,
              status: 'running',
              text: descriptiveName
            }];
          });
        } else if (chunk.type === 'tool_end') {
          setThinkingSteps(prev =>
            prev.map(s => s.tool === chunk.tool ? { ...s, status: 'complete' } : s)
          );
        } else if (chunk.type === 'complete') {
          setMessages(prev =>
            prev.map(m => m.id === aiMsgId ? {
              ...m,
              content: chunk.answer,
              citations: chunk.citations,
              sources: chunk.sources,
              tools_used: chunk.tools_used
            } : m)
          );
        } else if (chunk.type === 'error') {
          setMessages(prev =>
            prev.map(m => m.id === aiMsgId ? { ...m, content: m.content + `\n\n[Error: ${chunk.detail}]` } : m)
          );
        }
      }
    } catch (err) {
      setMessages(prev =>
        prev.map(m => m.id === aiMsgId ? { ...m, content: m.content + `\n\n[Streaming agent error: ${err.message}]` } : m)
      );
    } finally {
      setIsStreaming(false);
      setThinkingSteps([]);
    }
  };

  const handleAttachClick = () => {
    fileInputRef.current?.click();
  };

  return (
    <div 
      onDragEnter={handleDrag}
      onDragOver={handleDrag}
      className="flex h-screen bg-background text-on-surface font-body-md overflow-hidden relative"
    >
      {/* Full-Screen Drag and Drop Overlay */}
      <DragDropOverlay 
        dragActive={dragActive}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      />

      {/* Sidebar Navigation */}
      <Sidebar 
        user={user}
        sessions={sessions}
        activeSession={activeSession}
        documents={documents}
        onLogout={onLogout}
        setActiveSession={setActiveSession}
        onDeleteSession={handleDeleteSession}
        onCreateSession={handleCreateSession}
        onAttachClick={handleAttachClick}
      />

      {/* Main Content Area */}
      <main className="flex-1 h-screen flex flex-col relative bg-background">
        {/* Top Minimalist Header */}
        <header className="h-14 flex items-center justify-between px-6 border-b border-[#2f2f2f]/20 bg-zinc-950/20 backdrop-blur z-40 select-none">
          <div className="flex items-center gap-3">
            <span className="font-semibold text-sm text-zinc-200">
              {activeSession ? activeSession.title : 'Select a Session'}
            </span>
            {activeSession && documents.length > 0 && (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-zinc-850 border border-zinc-800 text-zinc-400 text-[10px] font-medium">
                <span className="material-symbols-outlined text-[10px]">folder</span>
                {documents.length} linked file{documents.length > 1 ? 's' : ''}
              </span>
            )}
          </div>
        </header>

        {/* Chat Scroll Canvas */}
        <ChatArea 
          activeSession={activeSession}
          messages={messages}
          isStreaming={isStreaming}
          thinkingSteps={thinkingSteps}
          messagesEndRef={messagesEndRef}
          setQuery={setQuery}
        />

        {/* Message Input prompt capsule */}
        <MessageInput 
          activeSession={activeSession}
          query={query}
          setQuery={setQuery}
          isStreaming={isStreaming}
          isUploading={isUploading}
          onSendMessage={handleSendMessage}
          onAttachClick={handleAttachClick}
        />
        
        {/* Hidden File Input Picker */}
        <input 
          type="file" 
          ref={fileInputRef}
          multiple
          accept=".pdf,.docx,.txt,.md,.csv"
          onChange={(e) => handleFileUpload(e.target.files)}
          className="hidden"
        />
      </main>
    </div>
  );
}
