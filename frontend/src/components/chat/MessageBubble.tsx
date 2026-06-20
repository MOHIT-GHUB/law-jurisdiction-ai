import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Message } from '../../types';
import { Scale } from 'lucide-react';

interface MessageBubbleProps {
  message: Message;
  isStreaming?: boolean;
}

export default function MessageBubble({ message, isStreaming }: MessageBubbleProps) {
  const isUser = message.role === 'user';

  return (
    <div className={`message-row ${isUser ? 'user' : 'assistant'}`}>
      {!isUser && (
        <div className="msg-avatar">
          <Scale size={14} />
        </div>
      )}
      <div className={`message-bubble ${isUser ? 'user' : 'assistant'} ${isStreaming ? 'streaming' : ''}`}>
        {isUser ? (
          <p>{message.content}</p>
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {message.content}
          </ReactMarkdown>
        )}
        {isStreaming && <span className="cursor-blink">▌</span>}
      </div>
    </div>
  );
}
