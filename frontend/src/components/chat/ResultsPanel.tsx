import { CheckCircle, Users, FileDown } from 'lucide-react';
import ScoreGauge from './ScoreGauge';
import LawyerCard from './LawyerCard';
import type { Lawyer } from '../../types';
import { conversationsApi } from '../../services/api';

interface ResultsPanelProps {
  score: number | null;
  lawyers: Lawyer[];
  actions: string[];
  conversationId: string;
  isComplete: boolean;
}

export default function ResultsPanel({ score, lawyers, actions, conversationId, isComplete }: ResultsPanelProps) {
  if (!score && lawyers.length === 0 && actions.length === 0) return null;

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
          <a
            href={conversationsApi.exportPdf(conversationId)}
            target="_blank"
            rel="noreferrer"
            className="export-btn"
          >
            <FileDown size={16} />
            Download full report (PDF)
          </a>
        </div>
      )}
    </div>
  );
}
