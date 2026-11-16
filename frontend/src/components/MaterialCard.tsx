// src/components/MaterialCard.tsx
import { Link } from 'react-router-dom';
import './MaterialCard.css';

interface MaterialCardProps {
  id: string;
  kind: 'course' | 'article' | 'document';
  title: string;
  description: string;
  duration: number | null;
  monetization: 'free' | 'subscription' | 'paid';
  icon: string;
  explanation?: string;
  isAuth?: boolean;
  isOnboardingDone?: boolean;
  lockedText?: string;
  stepNumber?: number;
}

export const MaterialCard = ({ 
  id, kind, title, description, duration, monetization, icon, 
  explanation, isAuth, lockedText, stepNumber 
}: MaterialCardProps) => {
  
  const formatDuration = () => {
    if (kind === 'document') return '';
    if (!duration) return '';
    if (duration < 60) return ` · ${duration} мин`;
    const hours = Math.floor(duration / 60);
    const mins = duration % 60;
    return ` · ${hours} ч${mins > 0 ? ` ${mins} мин` : ''}`;
  };

  const getMetaString = () => {
    const typeStr = kind === 'course' ? 'Курс' : kind === 'article' ? 'Статья' : 'Документ';
    const priceStr = monetization === 'free' ? 'Бесплатно' : monetization === 'subscription' ? 'Курс+' : '3 990 ₽';
    return `${typeStr}${formatDuration()} · ${priceStr}`;
  };

  const getLinkText = () => {
    if (kind === 'course') return 'Подробнее о курсе →';
    if (kind === 'article') return 'Читать статью →';
    return 'Скачать документ →';
  };

  return (
    <div className="material-card">
      <div className="card-top">
        <div className="card-icon">{icon}</div>
        {!stepNumber && <button className="bookmark-btn">🔖</button>}
      </div>

      <div className="card-content">
        {stepNumber && <div className="step-badge-inline">ШАГ {stepNumber}</div>}
        
        <h3 className="card-title">{title}</h3>
        <p className="card-description">{description}</p>
        
        {/* БЛОК С ОБЪЯСНЕНИЕМ */}
        {explanation && (
          <div className="card-ai-block">
            {isAuth ? (
              <span><strong>Почему вам подойдёт:</strong> {explanation}</span>
            ) : (
              <span className="ai-locked">
                {lockedText || 'Точка входа: базовый материал для старта.'}
              </span>
            )}
          </div>
        )}
      </div>

      <div className="card-footer">
        <span className="card-meta">{getMetaString()}</span>
        <Link to={`/material/${id}`} className="card-link">{getLinkText()}</Link>
      </div>
    </div>
  );
};