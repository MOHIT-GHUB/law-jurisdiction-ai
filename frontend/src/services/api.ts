import axios from 'axios';
import type { Conversation, User } from '../types';

const BASE_URL = import.meta.env.VITE_API_URL || '';

const api = axios.create({ baseURL: BASE_URL });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('lexai_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export const authApi = {
  signup: async (username: string, password: string): Promise<User> => {
    const { data } = await api.post('/auth/signup', { username, password });
    return { username: data.username, access_token: data.access_token };
  },
  login: async (username: string, password: string): Promise<User> => {
    const { data } = await api.post('/auth/login', { username, password });
    return { username: data.username, access_token: data.access_token };
  },
};

export const conversationsApi = {
  list: async (): Promise<Conversation[]> => {
    const { data } = await api.get('/conversations/');
    return data;
  },
  get: async (id: string): Promise<Conversation> => {
    const { data } = await api.get(`/conversations/${id}`);
    return data;
  },
  delete: async (id: string): Promise<void> => {
    await api.delete(`/conversations/${id}`);
  },
  exportPdf: (id: string): string => {
    const token = localStorage.getItem('lexai_token');
    return `${BASE_URL}/conversations/${id}/export-pdf?token=${token}`;
  },
};

export const createWebSocket = (conversationId: string): WebSocket => {
  const token = localStorage.getItem('lexai_token');
  const wsBase = (BASE_URL || window.location.origin).replace(/^http/, 'ws');
  return new WebSocket(`${wsBase}/ws/${conversationId}?token=${token}`);
};
