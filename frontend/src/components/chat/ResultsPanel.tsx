import { useState } from 'react';
import { CheckCircle, Users, FileDown, Loader2 } from 'lucide-react';
import ScoreGauge from './ScoreGauge';
import LawyerCard from './LawyerCard';
import type { Lawyer } from '../../types';

const BASE_URL = import.meta.env.VITE_API_URL || '';

interface ResultsPanelProps {
  score: number | null;
  lawyers: Lawyer[];
  actions: string[];
  conversationId: string;
  isComplete: boolean;
}

export default function ResultsPanel({ score, lawyers, actions, conversationId, isComplete }: ResultsPanelProps) {
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState('');

  if (!score && lawyers.length === 0 && actions.length === 0) return null;

  const handleExport = async () => {
    setDownloading(true);
    setDownloadError('');
    try {
      const token = localStorage.getItem('lexai_token');
      const res = await fetch(`${BASE_URL}/conversations/${conversationId}/export-pdf`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Error ${res.status}`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `lexai-report-${conversationId.slice(0, 8)}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err: unknown) {
      setDownloadError((err as Error).message || 'Download failed');
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="results-panel">
      {score !== null && (
        <div className="results-section">
          <ScoreGauge score={score} />
        </div>
      )}

      {actions.length > 0 && (
        <div className="results-section">
          <div className="results-section-title">
            <CheckCircle size={15} />
            Recommended next steps
          </div>
          <ol className="actions-list">
            {actions.map((action, i) => (
              <li key={i} className="action-item">
                <span className="action-num">{i + 1}</span>
                <span>{action}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {lawyers.length > 0 && (
        <div className="results-section">
          <div className="results-section-title">
            <Users size={15} />
            Attorneys near you
          </div>
          <div className="lawyers-list">
            {lawyers.map((l, i) => (
              <LawyerCard key={i} lawyer={l} index={i} />
            ))}
          </div>
        </div>
      )}

      {isComplete && (
        <div className="results-section">
          <button className="export-btn" onClick={handleExport} disabled={downloading}>
            {downloading ? <Loader2 size={16} className="spin" /> : <FileDown size={16} />}
            {downloading ? 'Generating PDF...' : 'Download full report (PDF)'}
          </button>
          {downloadError && (
            <div style={{ fontSize: 12, color: 'var(--red)', marginTop: 6 }}>{downloadError}</div>
          )}
        </div>
      )}
    </div>
  );
}