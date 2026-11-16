// src/components/Footer.tsx
import { Link } from 'react-router-dom';
import './Footer.css';

interface FooterProps {
  onRecommendationsClick?: () => void;
}

export const Footer = ({ onRecommendationsClick }: FooterProps) => {
  return (
    <footer className="footer">
      <div className="footer-container">
        <div className="footer-top">
          <div className="footer-brand">
            <div className="footer-logo">
              <span className="logo-a">A</span>
              <span className="logo-text">Альфа Банк</span>
            </div>
            <span className="footer-separator">|</span>
            <span className="footer-brand-name">Альфа-Курс</span>
          </div>

          <div className="footer-links">
            <button onClick={onRecommendationsClick} className="footer-link-btn">
              Рекомендации
            </button>
            <Link to="/profile">Моя траектория</Link>
          </div>
        </div>

        <div className="footer-bottom">
          <div className="footer-copy">
            <p>© Альфа-Банк, 2026</p>
            <p>Обучение для развития вашего бизнеса</p>
          </div>
        </div>
      </div>
    </footer>
  );
};