export interface User {
  username: string;
  access_token: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string | null;
  state: 'intake' | 'active' | 'completed';
  created_at: string;
  intake_summary: Record<string, string> | null;
  research_result: ResearchResult | null;
  messages?: Message[];
}

export interface ResearchResult {
  opinion: string;
  case_strength_score: number;
  recommended_actions: string[];
  referred_lawyers: Lawyer[];
  federal_law_results: LawResult[];
  state_law_results: LawResult[];
  case_law_results: LawResult[];
}

export interface Lawyer {
  name: string;
  firm?: string;
  address?: string;
  phone?: string;
  distance?: string;
  specialty?: string;
  rating?: number;
}

export interface LawResult {
  title: string;
  url?: string;
  summary?: string;
  citation?: string;
}

export type WSMessage =
  | { type: 'token'; content: string }
  | { type: 'status'; message: string }
  | { type: 'intake_complete' }
  | { type: 'score'; value: number }
  | { type: 'lawyers'; data: Lawyer[] }
  | { type: 'actions'; data: string[] }
  | { type: 'done' }
  | { type: 'error'; message: string };
