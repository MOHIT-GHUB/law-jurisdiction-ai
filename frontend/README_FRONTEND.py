"""
frontend/ — React TypeScript frontend for LexAI.

═══════════════════════════════════════════════════════════════
  ARCHITECTURE DIAGRAM MAPPING
═══════════════════════════════════════════════════════════════

  "Client — ChatGPT-like Chat System" in the diagram = this folder.

  The frontend is a single-page React app that looks and works
  like ChatGPT — sidebar with history, chat window, streaming
  responses. But with two unique visual elements judges will
  remember:
    1. Case Strength Score (animated 0-100 gauge)
    2. Attorney referral cards with ratings

═══════════════════════════════════════════════════════════════
  COMPONENT MAP (what to build and what each does)
═══════════════════════════════════════════════════════════════

  src/
  ├── App.tsx
  │     Root. Handles routing:
  │       /        → AuthPage (if not logged in)
  │       /chat    → ChatLayout (if logged in)
  │
  ├── pages/
  │   ├── AuthPage.tsx
  │   │     Login + Signup form.
  │   │     API calls: POST /auth/login, POST /auth/signup
  │   │     On success: store JWT in localStorage, redirect to /chat
  │   │
  │   └── ChatLayout.tsx
  │         Root layout: Sidebar (left) + ChatWindow (right)
  │
  ├── components/
  │   ├── Sidebar.tsx
  │   │     Left panel — past conversations list.
  │   │     API call: GET /conversations/   (routers/conversations.py)
  │   │     Shows: conversation.title + conversation.created_at
  │   │     On click: load that conversation into ChatWindow
  │   │     Top button: "New Case" → starts a new WebSocket session
  │   │
  │   ├── ChatWindow.tsx          ← HARDEST COMPONENT
  │   │     Main chat area. Renders message bubbles.
  │   │     Connects via WebSocket: ws://localhost:8000/ws/{id}?token=JWT
  │   │     Handles incoming JSON messages:
  │   │       {type:"token"}         → append to current assistant bubble
  │   │       {type:"intake_complete"} → show "Researching your case..." spinner
  │   │       {type:"score"}         → render ScoreCard component
  │   │       {type:"lawyers"}       → render LawyerCard components
  │   │       {type:"done"}          → show ExportButton
  │   │       {type:"error"}         → show inline error message
  │   │     Key feature: Markdown rendering of assistant messages
  │   │     Key feature: "Researching..." typing indicator during research phase
  │   │
  │   ├── ScoreCard.tsx            ← WIN FACTOR — make this look impressive
  │   │     Displays the Case Strength Score (0-100).
  │   │     Props: score: number
  │   │     Visual: animated circular progress gauge OR progress bar
  │   │     Color:  0-30  = red   (#ef4444)
  │   │             31-60 = amber (#f59e0b)
  │   │             61-85 = green (#22c55e)
  │   │             86-100= dark green (#15803d)
  │   │     Label:  "Weak" / "Moderate" / "Strong" / "Very Strong"
  │   │     Animation: count up from 0 to score on reveal
  │   │
  │   ├── LawyerCard.tsx
  │   │     Shows a referred attorney.
  │   │     Props: name, address, rating, specialty, url
  │   │     Visual: card with star rating, Google Maps link
  │   │
  │   ├── ExportButton.tsx
  │   │     "Download Report (PDF)" button.
  │   │     On click: fetch GET /conversations/{id}/export-pdf
  │   │               with Authorization header
  │   │               trigger browser download
  │   │
  │   └── MessageBubble.tsx
  │         Renders a single chat message.
  │         user messages: right-aligned, blue bubble
  │         assistant messages: left-aligned, white/gray, markdown rendered
  │
  ├── hooks/
  │   ├── useWebSocket.ts
  │   │     Custom hook managing the WebSocket connection.
  │   │     Exposes: sendMessage(), messages[], isConnected, isResearching
  │   │     Reconnect logic on disconnect.
  │   │
  │   └── useAuth.ts
  │         Manages JWT token in localStorage.
  │         Exposes: token, username, login(), logout()
  │
  ├── api/
  │   └── client.ts
  │         Axios or fetch wrapper with base URL + auth header.
  │         All REST calls go through here (not WebSocket calls).
  │
  └── types/
      └── index.ts
            TypeScript types matching backend schemas:
              interface Conversation { id, title, state, created_at, ... }
              interface Message { id, role, content, created_at }
              type WsMessage = TokenMsg | ScoreMsg | LawyerMsg | DoneMsg | ErrorMsg

═══════════════════════════════════════════════════════════════
  HOW TO CREATE THE PROJECT
═══════════════════════════════════════════════════════════════

  cd d:/LAW
  npm create vite@latest frontend -- --template react-ts
  cd frontend
  npm install
  npm install tailwindcss @tailwindcss/vite react-markdown
  npm install react-router-dom axios

  Then use v0.dev (https://v0.dev) to generate:
    - The ChatWindow component (show it a ChatGPT screenshot)
    - The ScoreCard component (describe the gauge design)
  Paste generated code into the components/ folder and adjust imports.

═══════════════════════════════════════════════════════════════
  TEAM — EFFORT ESTIMATE
═══════════════════════════════════════════════════════════════

  AuthPage.tsx       30 min  (ask ChatGPT for a login/signup form)
  Sidebar.tsx        45 min
  ChatWindow.tsx     3-4 hours  ← start early, hardest frontend piece
  ScoreCard.tsx      1 hour  (find a React gauge library or use CSS)
  LawyerCard.tsx     30 min
  ExportButton.tsx   20 min
  useWebSocket.ts    1-2 hours
  useAuth.ts         30 min
  Total:             ~8-10 hours
"""

# This file is a placeholder. Run the commands above to create the frontend.
