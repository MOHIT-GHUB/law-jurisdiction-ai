import { MapPin, Phone, Star, Briefcase, ExternalLink } from 'lucide-react';
import type { Lawyer } from '../../types';

interface LawyerCardProps {
  lawyer: Lawyer;
  index: number;
}

export default function LawyerCard({ lawyer, index }: LawyerCardProps) {
  return (
    <div className="lawyer-card" style={{ animationDelay: `${index * 0.1}s` }}>
      <div className="lawyer-avatar">{lawyer.name[0]}</div>
      <div className="lawyer-info">
        {lawyer.url ? (
          <a
            className="lawyer-name lawyer-name-link"
            href={lawyer.url}
            target="_blank"
            rel="noopener noreferrer"
          >
            {lawyer.name}
            <ExternalLink size={11} />
          </a>
        ) : (
          <div className="lawyer-name">{lawyer.name}</div>
        )}
        {lawyer.firm && <div className="lawyer-firm">{lawyer.firm}</div>}
        <div className="lawyer-details">
          {lawyer.specialty && (
            <span className="lawyer-tag">
              <Briefcase size={11} />
              {lawyer.specialty}
            </span>
          )}
          {lawyer.rating && (
            <span className="lawyer-tag">
              <Star size={11} />
              {lawyer.rating.toFixed(1)}
            </span>
          )}
          {lawyer.distance && (
            <span className="lawyer-tag">
              <MapPin size={11} />
              {lawyer.distance}
            </span>
          )}
        </div>
        {lawyer.address && (
          <div className="lawyer-address">
            <MapPin size={12} />
            {lawyer.address}
          </div>
        )}
        {lawyer.phone && (
          <a href={`tel:${lawyer.phone}`} className="lawyer-phone">
            <Phone size={12} />
            {lawyer.phone}
          </a>
        )}
      </div>
    </div>
  );
}
