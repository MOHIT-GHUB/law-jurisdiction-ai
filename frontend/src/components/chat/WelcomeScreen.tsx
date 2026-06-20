import { Scale, Shield, Search, Users } from 'lucide-react';

interface WelcomeScreenProps {
  onStart: (prompt: string) => void;
}

const EXAMPLE_PROMPTS = [
  'My landlord entered my apartment without notice and I think it violates my rights.',
  'I was fired last week after reporting a safety violation to HR.',
  'My employer hasn\'t paid my overtime for the past 3 months.',
  'I was in a car accident and the other driver was uninsured.',
];

export default function WelcomeScreen({ onStart }: WelcomeScreenProps) {
  return (
    <div className="welcome-screen">
      <div className="welcome-content">
        <div className="welcome-icon">
          <Scale size={40} />
        </div>
        <h2>How can I help with your legal situation?</h2>
        <p>Describe what happened in plain language. I'll research the applicable federal and state laws, find relevant case precedents, and assess the strength of your case.</p>

        <div className="welcome-features">
          <div className="welcome-feature">
            <Search size={18} />
            <div>
              <strong>Multi-jurisdiction research</strong>
              <span>Federal statutes, state law, and case precedents</span>
            </div>
          </div>
          <div className="welcome-feature">
            <Shield size={18} />
            <div>
              <strong>Case strength analysis</strong>
              <span>0–100 score based on legal merit</span>
            </div>
          </div>
          <div className="welcome-feature">
            <Users size={18} />
            <div>
              <strong>Attorney referrals</strong>
              <span>Nearby lawyers who handle your type of case</span>
            </div>
          </div>
        </div>

        <div className="example-prompts">
          <div className="examples-label">Try an example</div>
          <div className="examples-grid">
            {EXAMPLE_PROMPTS.map((prompt, i) => (
              <button
                key={i}
                className="example-btn"
                onClick={() => onStart(prompt)}
              >
                {prompt}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
