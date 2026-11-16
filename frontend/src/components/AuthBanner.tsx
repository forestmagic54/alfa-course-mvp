// src/components/AuthBanner.tsx
import './AuthBanner.css';

interface AuthBannerProps {
  variant: 'personal' | 'trajectory';
  onLoginClick: () => void;
}

export const AuthBanner = ({ variant, onLoginClick }: AuthBannerProps) => {
  if (variant === 'trajectory') {
    return (
      <div className="auth-banner auth-banner--trajectory">
        <div className="auth-banner-content">
          <h3>Маршрут из 3 материалов по вашей задаче</h3>
          <p>Авторизуйтесь, чтобы сохранить прогресс, открыть персональный разбор каждого шага и забрать бонус 24 часа на Курс+</p>
        </div>
        <button className="btn-primary" onClick={onLoginClick}>Войти и сохранить</button>
      </div>
    );
  }

  return (
    <div className="auth-banner auth-banner--personal">
      <div className="auth-banner-content">
        <span>Персональный разбор каждого материала под ваш бизнес доступен после входа</span>
      </div>
      <button className="auth-banner-link" onClick={onLoginClick}>Войти в профиль →</button>
    </div>
  );
};