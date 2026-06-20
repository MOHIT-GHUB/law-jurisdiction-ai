import { useState, useRef, useCallback } from 'react';
import { v4 as uuidv4 } from 'uuid';
import type { Message, Lawyer, WSMessage } from '../types';
import { createWebSocket } from '../services/api';

export interface ChatState {
  messages: Message[];
  isThinking: boolean;
  statusText: string;
  streamingContent: string;
  score: number | null;
  lawyers: Lawyer[];
  actions: string[];
  isComplete: boolean;
  error: string | null;
}

export function useChat(conversationId: string) {
  const wsRef = useRef<WebSocket | null>(null);
  const [state, setState] = useState<ChatState>({
    messages: [],
    isThinking: false,
    statusText: '',
    streamingContent: '',
    score: null,
    lawyers: [],
    actions: [],
    isComplete: false,
    error: null,
  });

  const initMessages = useCallback((msgs: Message[]) => {
    setState(s => ({ ...s, messages: msgs }));
  }, []);

  const sendMessage = useCallback((content: string) => {
    if (!content.trim()) return;

    const userMsg: Message = {
      id: uuidv4(),
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    };

    setState(s => ({
      ...s,
      messages: [...s.messages, userMsg],
      isThinking: true,
      statusText: 'Connecting...',
      streamingContent: '',
      error: null,
    }));

    // Create WS if not open
    if (!wsRef.current || wsRef.current.readyState > 1) {
      wsRef.current = createWebSocket(conversationId);
    }

    let assembledContent = '';

    const ws = wsRef.current;

    const send = () => ws.send(JSON.stringify({ type: 'message', content }));

    if (ws.readyState === WebSocket.OPEN) {
      send();
    } else {
      ws.onopen = () => send();
    }

    ws.onmessage = (event) => {
      const msg: WSMessage = JSON.parse(event.data);

      switch (msg.type) {
        case 'token':
          assembledContent += msg.content;
          setState(s => ({ ...s, streamingContent: assembledContent, statusText: '' }));
          break;
        case 'status':
          setState(s => ({ ...s, statusText: msg.message }));
          break;
        case 'intake_complete':
          setState(s => ({ ...s, statusText: 'Researching federal law, state law, and case precedents...' }));
          break;
        case 'score':
          setState(s => ({ ...s, score: msg.value }));
          break;
        case 'lawyers':
          setState(s => ({ ...s, lawyers: msg.data }));
          break;
        case 'actions':
          setState(s => ({ ...s, actions: msg.data }));
          break;
        case 'done': {
          const assistantMsg: Message = {
            id: uuidv4(),
            role: 'assistant',
            content: assembledContent,
            created_at: new Date().toISOString(),
          };
          setState(s => ({
            ...s,
            messages: [...s.messages, assistantMsg],
            streamingContent: '',
            isThinking: false,
            statusText: '',
            isComplete: true,
          }));
          break;
        }
        case 'error':
          setState(s => ({
            ...s,
            isThinking: false,
            statusText: '',
            streamingContent: '',
            error: msg.message,
          }));
          break;
      }
    };

    ws.onerror = () => {
      setState(s => ({
        ...s,
        isThinking: false,
        error: 'Connection error. Please try again.',
      }));
    };
  }, [conversationId]);

  return { state, sendMessage, initMessages };
}
