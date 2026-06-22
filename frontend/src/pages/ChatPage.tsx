import { useEffect, useRef, useState, useCallback } from 'react';
import { AlertCircle, Scale, Loader2 } from 'lucide-react';
import { useChat } from '../hooks/useChat';
import { conversationsApi } from '../services/api';
import MessageBubble from '../components/chat/MessageBubble';
import ChatInput from '../components/chat/ChatInput';
import WelcomeScreen from '../components/chat/WelcomeScreen';
import ResultsPanel from '../components/chat/ResultsPanel';
import type { Message, ResearchResult } from '../types';

interface ChatPageProps {
  conversationId: string;
  onConversationReady: () => void;
}

export default function ChatPage({ conversationId, onConversationReady }: ChatPageProps) {
  const { state, sendMessage, initMessages } = useChat(conversationId);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [restoredResult, setRestoredResult] = useState<ResearchResult | null>(null);
  const [loadingConv, setLoadingConv] = useState(true);

  useEffect(() => {
    // ChatPage is remounted on conversationId change (see key={conversationId} in
    // App), so initial state is already fresh — just load this conversation's
    // history + saved results.
    let cancelled = false;

    conversationsApi.list()
      .then(list => {
        const exists = list.some(c => c.id === conversationId);
        if (!exists) {
          if (!cancelled) setLoadingConv(false);
          return;
        }
        return conversationsApi.get(conversationId).then(conv => {
          if (cancelled) return;
          if (conv.messages && conv.messages.length > 0) {
            initMessages(conv.messages as Message[]);
          }
          if (conv.research_result) {
            setRestoredResult(conv.research_result);
          }
          setLoadingConv(false);
        });
      })
      .catch(() => {
        if (!cancelled) setLoadingConv(false);
      });

    return () => { cancelled = true; };
  }, [conversationId, initMessages]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [state.messages, state.streamingContent]);

  const handleSend = useCallback((content: string) => {
    sendMessage(content);
    onConversationReady();
  }, [sendMessage, onConversationReady]);

  const score = state.score ?? restoredResult?.case_strength_score ?? null;
  const lawyers = state.lawyers.length > 0 ? state.lawyers : (restoredResult?.referred_lawyers ?? []);
  const actions = state.actions.length > 0 ? state.actions : (restoredResult?.recommended_actions ?? []);
  const hasResults = score !== null || lawyers.length > 0 || actions.length > 0;
  const isEmpty = state.messages.length === 0 && !state.streamingContent;

  if (loadingConv) {
    return (
      <div className="chat-page">
        <div className="chat-main" style={{ alignItems: 'center', justifyContent: 'center' }}>
          <Loader2 size={28} className="spin" style={{ color: 'var(--text-dim)' }} />
        </div>
      </div>
    );
  }

  return (
    <div className="chat-page">
      <div className="chat-main">
        {isEmpty ? (
          <WelcomeScreen onStart={handleSend} />
        ) : (
          <div className="messages-area">
            <div className="messages-list">
              {state.messages.map(msg => (
                <MessageBubble key={msg.id} message={msg} />
              ))}

              {state.streamingContent && (
                <MessageBubble
                  message={{
                    id: 'streaming',
                    role: 'assistant',
                    content: state.streamingContent,
                    created_at: new Date().toISOString(),
                  }}
                  isStreaming
                />
              )}

              {state.isThinking && !state.streamingContent && (
                <div className="status-row">
                  <div className="msg-avatar">
                    <Scale size={14} />
                  </div>
                  <div className="status-indicator">
                    <div className="thinking-dots">
                      <span /><span /><span />
                    </div>
                    {state.statusText && (
                      <span className="status-text">{state.statusText}</span>
                    )}
                  </div>
                </div>
              )}

              {state.isThinking && state.streamingContent && state.statusText && (
                <div className="status-inline">{state.statusText}</div>
              )}

              {state.error && (
                <div className="error-row">
                  <AlertCircle size={16} />
                  {state.error}
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          </div>
        )}

        <ChatInput
          onSend={handleSend}
          disabled={state.isThinking}
          placeholder={
            isEmpty
              ? 'Describe your legal situation in plain language...'
              : 'Ask a follow-up question...'
          }
        />
      </div>

      {hasResults && (
        <aside className="results-sidebar">
          <ResultsPanel
            score={score}
            lawyers={lawyers}
            actions={actions}
            conversationId={conversationId}
            isComplete={state.isComplete || restoredResult !== null}
          />
        </aside>
      )}
    </div>
  );
}
