export default function MessageInput({ 
  activeSession, 
  query, 
  setQuery, 
  isStreaming, 
  isUploading, 
  onSendMessage, 
  onAttachClick 
}) {
  if (!activeSession) return null;

  return (
    <div className="absolute bottom-0 left-0 w-full bg-gradient-to-t from-background via-background/95 to-transparent pt-6 pb-4">
      <div className="w-full max-w-2xl mx-auto px-4 select-none">
        <form onSubmit={onSendMessage} className="relative group">
          <div className="relative flex flex-col bg-zinc-900 border border-zinc-800 rounded-2xl p-1.5 focus-within:border-zinc-750 transition-colors shadow-2xl">
            <textarea 
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  onSendMessage(e);
                }
              }}
              className="w-full bg-transparent border-none focus:ring-0 text-zinc-200 text-sm py-2 px-3 resize-none max-h-36 placeholder-zinc-650 outline-none" 
              placeholder="Message Lumen..." 
              rows={2}
            />
            <div className="flex items-center justify-between border-t border-zinc-850/50 pt-1.5 px-1 pb-0.5">
              <button 
                type="button"
                onClick={onAttachClick}
                className="p-1.5 text-zinc-500 hover:text-zinc-350 transition-colors cursor-pointer rounded-lg hover:bg-zinc-800/60"
                title="Upload Documents"
              >
                <span className="material-symbols-outlined text-lg">attach_file</span>
              </button>
              
              <div className="flex items-center gap-2">
                {isUploading && (
                  <span className="text-[10px] text-zinc-500 animate-pulse flex items-center gap-1">
                    <span className="material-symbols-outlined text-xs animate-spin" style={{ animationDuration: '2s' }}>progress_activity</span>
                    Uploading...
                  </span>
                )}
                <button 
                  type="submit"
                  disabled={!query.trim() || isStreaming}
                  className={`w-8 h-8 rounded-full flex items-center justify-center transition-all ${
                    query.trim() && !isStreaming
                      ? 'bg-primary text-white cursor-pointer hover:scale-105 active:scale-95'
                      : 'bg-zinc-800 text-zinc-655 cursor-not-allowed'
                  }`}
                >
                  <span className="material-symbols-outlined text-sm font-bold" style={{ fontVariationSettings: "'FILL' 1" }}>arrow_upward</span>
                </button>
              </div>
            </div>
          </div>
          <p className="text-[9px] text-zinc-600 text-center mt-2">
            Lumen can make mistakes. Consider checking important information.
          </p>
        </form>
      </div>
    </div>
  );
}
