import { useEffect, useRef, useState, useCallback } from 'react';
import { v4 as uuidv4 } from 'uuid';
import { Loader2, AlertCircle, Scale } from 'lucide-react';
import { useChat } from '../hooks/useChat';
import { conversationsApi } from '../services/api';
import MessageBubble from '../components/chat/MessageBubble';
import ChatInput from '../components/chat/ChatInput';
import WelcomeScreen from '../components/chat/WelcomeScreen';
import ResultsPanel from '../components/chat/ResultsPanel';
import type { Message } from '../types';

interface ChatPageProps {
  conversationId: string;
  onConversationReady: () => void;
}

export default function ChatPage({ conversationId, onConversationReady }: ChatPageProps) {
  const { state, sendMessage, initMessages } = useChat(conversationId);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);

  // Load existing messages when switching conversations
  useEffect(() => {
    setLoaded(true);
  }, [conversationId]);

  // Auto scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [state.messages, state.streamingContent]);

  const handleSend = useCallback((content: string) => {
    sendMessage(content);
    onConversationReady();
  }, [sendMessage, onConversationReady]);

  const isEmpty = state.messages.length === 0 && !state.streamingContent;
  const hasResults = state.score !== null || state.lawyers.length > 0 || state.actions.length > 0;

  

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

              {/* Streaming assistant message */}
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

              {/* Status indicator */}
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

              {/* Status text while streaming */}
              {state.isThinking && state.streamingContent && state.statusText && (
                <div className="status-inline">{state.statusText}</div>
              )}

              {/* Error */}
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
            score={state.score}
            lawyers={state.lawyers}
            actions={state.actions}
            conversationId={conversationId}
            isComplete={state.isComplete}
          />
        </aside>
      )}
    </div>
  );
}
