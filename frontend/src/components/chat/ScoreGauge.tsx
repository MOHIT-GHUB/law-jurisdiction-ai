import { useEffect, useState } from 'react';

interface ScoreGaugeProps {
  score: number;
}

function getScoreColor(score: number): string {
  if (score >= 70) return '#22c55e';
  if (score >= 45) return '#f59e0b';
  return '#ef4444';
}

function getScoreLabel(score: number): string {
  if (score >= 75) return 'Strong case';
  if (score >= 55) return 'Moderate case';
  if (score >= 35) return 'Challenging case';
  return 'Difficult case';
}

export default function ScoreGauge({ score }: ScoreGaugeProps) {
  const [displayed, setDisplayed] = useState(0);

  useEffect(() => {
    let frame: number;
    let current = 0;
    const step = () => {
      current = Math.min(current + 1.5, score);
      setDisplayed(Math.round(current));
      if (current < score) frame = requestAnimationFrame(step);
    };
    const timeout = setTimeout(() => { frame = requestAnimationFrame(step); }, 400);
    return () => { clearTimeout(timeout); cancelAnimationFrame(frame); };
  }, [score]);

  const color = getScoreColor(score);
  const circumference = 2 * Math.PI * 54;
  const dashOffset = circumference - (displayed / 100) * circumference;

  return (
    <div className="score-gauge">
      <div className="score-ring-wrap">
        <svg width="128" height="128" viewBox="0 0 128 128">
          <circle cx="64" cy="64" r="54" fill="none" stroke="#1e2d4a" strokeWidth="10" />
          <circle
            cx="64" cy="64" r="54"
            fill="none"
            stroke={color}
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            transform="rotate(-90 64 64)"
            style={{ transition: 'stroke-dashoffset 0.05s linear', filter: `drop-shadow(0 0 6px ${color}66)` }}
          />
        </svg>
        <div className="score-center">
          <span className="score-number" style={{ color }}>{displayed}</span>
          <span className="score-pct">/ 100</span>
        </div>
      </div>
      <div className="score-meta">
        <div className="score-label" style={{ color }}>{getScoreLabel(score)}</div>
        <div className="score-sublabel">Case strength score</div>
      </div>
    </div>
  );
}
