import { useState, useCallback } from 'react';
import { v4 as uuidv4 } from 'uuid';
import { AuthProvider, useAuth } from './hooks/useAuth';
import AuthPage from './pages/AuthPage';
import ChatPage from './pages/ChatPage';
import Sidebar from './components/layout/Sidebar';

function AppInner() {
  const { user } = useAuth();
  const [conversationId, setConversationId] = useState<string>(() => uuidv4());
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const handleNew = useCallback(() => {
    setConversationId(uuidv4());
  }, []);

  const handleSelect = useCallback((id: string) => {
    setConversationId(id);
  }, []);

  const handleConversationReady = useCallback(() => {
    setRefreshTrigger(n => n + 1);
  }, []);

  if (!user) return <AuthPage />;

  return (
    <div className="app-shell">
      <Sidebar
        activeId={conversationId}
        onSelect={handleSelect}
        onNew={handleNew}
        refreshTrigger={refreshTrigger}
      />
      <main className="app-main">
        <ChatPage
          key={conversationId}
          conversationId={conversationId}
          onConversationReady={handleConversationReady}
        />
      </main>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppInner />
    </AuthProvider>
  );
}
