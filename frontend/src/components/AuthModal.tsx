// src/components/AuthModal.tsx
import { useState } from 'react';
import { login } from '../api';
import './AuthModal.css';

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const AuthModal = ({ isOpen, onClose }: AuthModalProps) => {
  const [authMethod, setAuthMethod] = useState<'alfa' | 'email'>('alfa');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  if (!isOpen) return null;

  const handleLogin = async () => {
    if (!email || !password) {
      setError('Введите email и пароль');
      return;
    }
    const result = await login(email, password);
    if (result) {
      onClose();
      window.location.reload(); // Перезагрузка, чтобы HomePage прочитал токен
    } else {
      setError('Неверный email или пароль');
    }
  };

  return (
    <div className="auth-overlay" onClick={onClose}>
      <div className="auth-modal" onClick={(e) => e.stopPropagation()}>
        
        {/* Левая красная часть */}
        <div className="auth-left">
          <div className="auth-logo">
            <span className="logo-a">A</span>
            <div>
              <div className="logo-title">Альфа-Курс</div>
              <div className="logo-sub">Обучение для развития бизнеса</div>
            </div>
          </div>
          
          <div className="auth-promo">
            <span className="promo-badge">Личный кабинет</span>
            <h2>Сохраняйте прогресс и учитесь в удобном темпе</h2>
            <p>Доступ к персональной витрине, материалам и специальным предложениям платформы в едином личном кабинете.</p>
          </div>

          <div className="auth-footer-left">
            © 2026 Альфа-Банк
          </div>
        </div>

        {/* Правая белая часть */}
        <div className="auth-right">
          <button className="auth-close" onClick={onClose}>✕</button>
          
          <div className="auth-header">
            <span className="auth-step">● Защищённый вход</span>
            <h2>Войти в Альфа-Курс</h2>
            <p>Авторизуйтесь, чтобы сохранить подборку и продолжить обучение.</p>
          </div>

          <div className="auth-tabs">
            <button 
              className={`auth-tab ${authMethod === 'alfa' ? 'active' : ''}`}
              onClick={() => setAuthMethod('alfa')}
            >
              <span className="alfa-icon">A</span> Альфа ID
            </button>
            <button 
              className={`auth-tab ${authMethod === 'email' ? 'active' : ''}`}
              onClick={() => setAuthMethod('email')}
            >
              Почта
            </button>
          </div>

          {authMethod === 'alfa' && (
            <div className="auth-form">
              <p className="alfa-id-hint">
                Используйте ваш Альфа ID для быстрого и безопасного входа в личный кабинет.
              </p>
              <button className="btn-primary w-100" onClick={() => handleLogin()}>
                Войти с Альфа ID
              </button>
            </div>
          )}

          {authMethod === 'email' && (
            <div className="auth-form">
              <div className="input-group">
                <span className="input-icon">✉️</span>
                <input 
                  type="email" 
                  placeholder="example@yandex.ru" 
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <div className="input-group" style={{ marginTop: '12px' }}>
                <span className="input-icon">🔒</span>
                <input 
                  type="password" 
                  placeholder="Пароль" 
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
              
              {error && <p style={{ color: 'red', fontSize: '12px' }}>{error}</p>}

              <button className="btn-primary w-100" onClick={handleLogin}>
                Войти
              </button>
            </div>
          )}

          <div className="auth-legal">
            Продолжая, вы принимаете <a href="#">условия использования</a> и <a href="#">политику конфиденциальности</a>
          </div>
        </div>
      </div>
    </div>
  );
};