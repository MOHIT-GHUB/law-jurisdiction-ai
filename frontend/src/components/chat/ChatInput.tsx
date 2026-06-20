import { useState, useRef, useEffect } from 'react';
import { ArrowUp, Loader2 } from 'lucide-react';

interface ChatInputProps {
  onSend: (msg: string) => void;
  disabled: boolean;
  placeholder?: string;
}

export default function ChatInput({ onSend, disabled, placeholder }: ChatInputProps) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 160) + 'px';
    }
  }, [value]);

  const handleSend = () => {
    if (!value.trim() || disabled) return;
    onSend(value.trim());
    setValue('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  };

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="chat-input-wrap">
      <div className="chat-input-inner">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={handleKey}
          placeholder={placeholder || 'Describe your legal situation...'}
          disabled={disabled}
          rows={1}
          className="chat-textarea"
        />
        <button
          className={`send-btn ${value.trim() && !disabled ? 'active' : ''}`}
          onClick={handleSend}
          disabled={!value.trim() || disabled}
          aria-label="Send"
        >
          {disabled ? <Loader2 size={18} className="spin" /> : <ArrowUp size={18} />}
        </button>
      </div>
      <div className="input-hint">
        Press Enter to send · Shift+Enter for new line
      </div>
    </div>
  );
}
