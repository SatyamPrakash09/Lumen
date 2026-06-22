import { useState, useEffect, useRef, useCallback } from 'react';
import { marked } from 'marked';

function CopyButton({ text, label = 'Copy', className = '' }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  }, [text]);

  return (
    <button
      onClick={handleCopy}
      className={`copy-btn ${copied ? 'copied' : ''} ${className}`}
      title={copied ? 'Copied!' : label}
    >
      <span className="material-symbols-outlined copy-btn-icon" style={{ fontVariationSettings: "'FILL' 0" }}>
        {copied ? 'check' : 'content_copy'}
      </span>
      <span className="copy-btn-label">{copied ? 'Copied!' : label}</span>
    </button>
  );
}

function MessageContent({ content }) {
  const contentRef = useRef(null);

  useEffect(() => {
    if (!contentRef.current) return;

    const preBlocks = contentRef.current.querySelectorAll('pre');
    preBlocks.forEach((pre) => {
      // Skip if already has a copy button
      if (pre.querySelector('.code-copy-btn')) return;

      // Wrap pre in a relative container
      pre.style.position = 'relative';

      const codeEl = pre.querySelector('code');
      const codeText = codeEl ? codeEl.textContent : pre.textContent;

      const btn = document.createElement('button');
      btn.className = 'code-copy-btn';
      btn.title = 'Copy code';
      btn.innerHTML = `<span class="material-symbols-outlined" style="font-variation-settings: 'FILL' 0; font-size: 14px;">content_copy</span>`;
      
      btn.addEventListener('click', async () => {
        try {
          await navigator.clipboard.writeText(codeText);
          btn.innerHTML = `<span class="material-symbols-outlined" style="font-variation-settings: 'FILL' 0; font-size: 14px;">check</span>`;
          btn.classList.add('copied');
          setTimeout(() => {
            btn.innerHTML = `<span class="material-symbols-outlined" style="font-variation-settings: 'FILL' 0; font-size: 14px;">content_copy</span>`;
            btn.classList.remove('copied');
          }, 2000);
        } catch (err) {
          console.error('Failed to copy code:', err);
        }
      });

      pre.appendChild(btn);
    });
  }, [content]);

  return (
    <div 
      ref={contentRef}
      className="markdown-content text-zinc-200 text-sm leading-relaxed"
      dangerouslySetInnerHTML={{ __html: marked.parse(content || '') }}
    />
  );
}

export default function ChatArea({ 
  activeSession, 
  messages, 
  isStreaming, 
  thinkingSteps, 
  messagesEndRef, 
  setQuery 
}) {
  if (!activeSession) {
    return (
      <div className="h-full flex flex-col justify-center items-center text-center px-4 max-w-lg mx-auto select-none">
        <span className="material-symbols-outlined text-primary text-5xl mb-3" style={{ fontVariationSettings: "'FILL' 0" }}>chat</span>
        <h3 className="text-2xl font-bold text-zinc-100">Welcome to Lumen</h3>
        <p className="text-zinc-405 text-xs mt-2 leading-relaxed">
          Select an existing chat session or create a new one in the sidebar to start questioning your knowledge base.
        </p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto py-6 px-6">
      {messages.length > 0 ? (
        <div className="max-w-2xl mx-auto space-y-8 pb-32">
          {messages.map((msg) => (
            <div 
              key={msg.id} 
              className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              {msg.sender === 'user' ? (
                /* User Prompt Capsule */
                <div className="bg-[#2f2f2f] text-zinc-100 rounded-2xl px-4 py-2.5 max-w-[70%] text-sm whitespace-pre-wrap leading-relaxed shadow-sm">
                  {msg.content}
                </div>
              ) : (
                /* AI Answer Block */
                <div className="flex justify-start w-full gap-4 py-2">
                  {/* AI Spark Icon */}
                  <div className="w-8 h-8 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center text-primary flex-shrink-0 shadow-sm">
                    <span className="material-symbols-outlined text-[18px]" style={{ fontVariationSettings: "'FILL' 1" }}>token</span>
                  </div>
                  
                  <div className="flex-1 space-y-4 min-w-0">
                    {/* Response text */}
                    <MessageContent content={msg.content} />

                    {/* Copy full response button */}
                    <div className="flex items-center gap-1 pt-1">
                      <CopyButton text={msg.content || ''} label="Copy" className="response-copy-btn" />
                    </div>

                    {/* Citation pills */}
                    {msg.citations && msg.citations.length > 0 && (
                      <div className="flex flex-wrap gap-2 pt-2">
                        {msg.citations.map((cite, i) => (
                          <a 
                            key={i} 
                            href={cite.url || '#'} 
                            target={cite.url ? "_blank" : undefined}
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1.5 bg-zinc-900 hover:bg-zinc-800 border border-zinc-855 rounded-lg px-2.5 py-1 text-xs text-zinc-300 transition-colors shadow-sm cursor-pointer"
                          >
                            <span className="material-symbols-outlined text-[13px] text-primary">
                              {cite.type === 'document' ? 'description' : 'language'}
                            </span>
                            <span className="truncate max-w-[150px] font-medium">{cite.title}</span>
                            {cite.page && <span className="text-zinc-500 text-[10px]">p.{cite.page}</span>}
                          </a>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}

          {/* Thinking accordion */}
          {isStreaming && thinkingSteps.length > 0 && (
            <div className="flex justify-start w-full gap-4">
              <div className="w-8 h-8 flex-shrink-0"></div>
              <div className="bg-zinc-900/60 border border-zinc-850/80 rounded-xl overflow-hidden max-w-[85%] shadow-sm">
                <details className="group" open>
                  <summary className="flex items-center gap-2 px-3.5 py-2 cursor-pointer select-none hover:bg-zinc-800/40 transition-colors">
                    <span className="material-symbols-outlined text-primary animate-spin text-[14px]" style={{ animationDuration: '2.5s' }}>progress_activity</span>
                    <span className="text-xs font-semibold text-zinc-400">RAG reasoning steps</span>
                    <span className="material-symbols-outlined ml-auto text-[14px] group-open:rotate-180 transition-transform">expand_more</span>
                  </summary>
                  <div className="px-3.5 pb-3 pt-1.5 border-t border-zinc-850/50 font-mono text-[10px] text-zinc-500 space-y-1.5">
                    {thinkingSteps.map((step, idx) => (
                      <div key={idx} className="flex gap-2">
                        <span className="text-zinc-600">[{idx + 1}]</span>
                        <span className={step.status === 'running' ? 'text-primary animate-pulse' : 'text-zinc-450'}>
                          {step.text}
                        </span>
                      </div>
                    ))}
                  </div>
                </details>
              </div>
            </div>
          )}

          {/* Streaming loading skeleton */}
          {isStreaming && messages[messages.length - 1]?.content === '' && (
            <div className="flex justify-start w-full gap-4 py-2">
              <div className="w-8 h-8 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center text-primary flex-shrink-0 animate-pulse">
                <span className="material-symbols-outlined text-[18px]" style={{ fontVariationSettings: "'FILL' 1" }}>token</span>
              </div>
              <div className="flex items-center gap-2 text-zinc-500 text-xs animate-pulse">
                <span className="material-symbols-outlined animate-spin text-[12px]" style={{ animationDuration: '2s' }}>progress_activity</span>
                Thinking...
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      ) : (
        /* Empty State Landing Dashboard */
        <div className="h-full flex flex-col justify-center items-center text-center px-4 max-w-lg mx-auto select-none">
          <span className="material-symbols-outlined text-primary text-5xl mb-3 animate-pulse-emerald" style={{ fontVariationSettings: "'FILL' 1" }}>token</span>
          <h3 className="text-2xl font-bold text-zinc-100">How can I help you today?</h3>
          <p className="text-zinc-450 text-xs mt-2 leading-relaxed">
            Upload your research paper, codebase, or spreadsheets. Lumen searches, analyzes, and synthesizes accurate responses supported by primary file sources and live web verifications.
          </p>
          
          <div className="grid grid-cols-2 gap-3 mt-8 w-full max-w-md">
            <div 
              onClick={() => setQuery("Summarize the key takeaways from my uploaded documents.")}
              className="p-3 bg-zinc-900/60 hover:bg-zinc-850/80 border border-zinc-850 hover:border-zinc-700/50 rounded-xl text-left cursor-pointer transition-all duration-200"
            >
              <p className="text-xs font-semibold text-zinc-200">Summarize documents</p>
              <p className="text-[10px] text-zinc-500 mt-1">Extract core takeaways from your files</p>
            </div>
            <div 
              onClick={() => setQuery("Are there any contradictions between my documents and the web?")}
              className="p-3 bg-zinc-900/60 hover:bg-zinc-850/80 border border-zinc-850 hover:border-zinc-700/50 rounded-xl text-left cursor-pointer transition-all duration-200"
            >
              <p className="text-xs font-semibold text-zinc-200">Cross-reference web</p>
              <p className="text-[10px] text-zinc-500 mt-1">Cross-check document claims with web search</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
