// src/components/Header.tsx
import { useNavigate } from 'react-router-dom';
import './Header.css';

interface HeaderProps {
  isAuth: boolean;
  onLoginClick: () => void;
}

export const Header = ({ isAuth, onLoginClick }: HeaderProps) => {
  const navigate = useNavigate();

  const handleProfileClick = () => {
    navigate('/profile');
  };

  return (
    <header className="header">
      <div className="header-container">
        <div className="header-logo" onClick={() => navigate('/')} style={{ cursor: 'pointer' }}>
          <span className="logo-a">A</span>
          <span className="logo-text">Альфа-Курс</span>
        </div>
        <div className="header-actions">
          {isAuth ? (
            <button className="btn-secondary" onClick={handleProfileClick}>
              Личный кабинет
            </button>
          ) : (
            <button className="btn-secondary" onClick={onLoginClick}>
              Войти
            </button>
          )}
        </div>
      </div>
    </header>
  );
};