import { useState, useEffect } from 'react';
import { Scale, Plus, Trash2, MessageSquare, LogOut, FileDown } from 'lucide-react';
import type { Conversation } from '../../types';
import { conversationsApi } from '../../services/api';
import { useAuth } from '../../hooks/useAuth';

interface SidebarProps {
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  refreshTrigger: number;
}

export default function Sidebar({ activeId, onSelect, onNew, refreshTrigger }: SidebarProps) {
  const { user, logout } = useAuth();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [deleting, setDeleting] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await conversationsApi.list();
        if (!cancelled) setConversations(data);
      } catch {
        // ignore
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshTrigger]);

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    setDeleting(id);
    try {
      await conversationsApi.delete(id);
      setConversations(c => c.filter(x => x.id !== id));
      if (activeId === id) onNew();
    } finally {
      setDeleting(null);
    }
  };

  const stateLabel = (state: string) => {
    if (state === 'completed') return <span className="state-badge completed">Done</span>;
    if (state === 'active') return <span className="state-badge active">Researching</span>;
    return <span className="state-badge intake">Intake</span>;
  };

  const formatDate = (iso: string) => {
    const d = new Date(iso);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    if (diff < 86400000) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    if (diff < 604800000) return d.toLocaleDateString([], { weekday: 'short' });
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  };

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="brand">
          <Scale size={20} />
          <span>LexAI</span>
        </div>
        <button className="new-chat-btn" onClick={onNew} title="New case">
          <Plus size={18} />
          <span>New case</span>
        </button>
      </div>

      <div className="sidebar-list">
        {conversations.length === 0 ? (
          <div className="sidebar-empty">
            <MessageSquare size={32} />
            <p>No cases yet</p>
            <span>Start a new case to get legal analysis</span>
          </div>
        ) : (
          <>
            <div className="sidebar-section-label">Recent cases</div>
            {conversations.map(conv => (
              <div
                key={conv.id}
                className={`sidebar-item ${activeId === conv.id ? 'active' : ''}`}
                onClick={() => onSelect(conv.id)}
              >
                <div className="sidebar-item-top">
                  <span className="sidebar-item-title">
                    {conv.title || 'Untitled case'}
                  </span>
                  <div className="sidebar-item-actions">
                    {conv.state === 'completed' && (
                      <a
                        href={conversationsApi.exportPdf(conv.id)}
                        target="_blank"
                        rel="noreferrer"
                        onClick={e => e.stopPropagation()}
                        title="Export PDF"
                        className="sidebar-action"
                      >
                        <FileDown size={14} />
                      </a>
                    )}
                    <button
                      className="sidebar-action danger"
                      onClick={e => handleDelete(e, conv.id)}
                      disabled={deleting === conv.id}
                      title="Delete case"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
                <div className="sidebar-item-meta">
                  {stateLabel(conv.state)}
                  <span className="sidebar-item-date">{formatDate(conv.created_at)}</span>
                  {conv.research_result?.case_strength_score ? (
                    <span className="sidebar-item-score">
                      {conv.research_result.case_strength_score}%
                    </span>
                  ) : null}
                </div>
              </div>
            ))}
          </>
        )}
      </div>

      <div className="sidebar-footer">
        <div className="sidebar-user">
          <div className="user-avatar">{user?.username[0].toUpperCase()}</div>
          <span className="user-name">{user?.username}</span>
        </div>
        <button className="logout-btn" onClick={logout} title="Sign out">
          <LogOut size={16} />
        </button>
      </div>
    </aside>
  );
}
