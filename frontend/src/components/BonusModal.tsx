// src/components/BonusModal.tsx
import { useState, useEffect } from 'react';
import './BonusModal.css';

interface BonusModalProps {
  isOpen: boolean;
  onClose: () => void;
  isAuth: boolean;
  onLoginClick: () => void;
  onBonusActivated?: () => void; // <-- ДОБАВЛЕН ПРОП
}

export const BonusModal = ({ isOpen, onClose, isAuth, onLoginClick, onBonusActivated }: BonusModalProps) => {
  const [isSuccess, setIsSuccess] = useState(false);
  const [timeLeft, setTimeLeft] = useState(24 * 60 * 60); // 24 часа в секундах

  // Таймер
  useEffect(() => {
    if (!isOpen || isSuccess) return;

    const timer = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [isOpen, isSuccess]);

  // Форматирование времени в ЧЧ:ММ:СС
  const formatTime = (seconds: number) => {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  if (!isOpen) return null;

  const handleActivate = () => {
    setIsSuccess(true);
    // Вызываем коллбэк, чтобы ProfilePage обновил подписку
    if (onBonusActivated) {
      onBonusActivated();
    }
  };

  const handleClose = () => {
    setIsSuccess(false);
    setTimeLeft(24 * 60 * 60); // Сбрасываем таймер при закрытии (опционально)
    onClose();
  };

  const handleGoToLogin = () => {
    handleClose();
    onLoginClick();
  };

  return (
    <div className="bonus-overlay" onClick={handleClose}>
      <div className="bonus-modal" onClick={(e) => e.stopPropagation()}>
        <button className="bonus-close" onClick={handleClose}>✕</button>

        {!isSuccess ? (
          <>
            <div className="bonus-header">
              <div className="bonus-badge">
                <span className="dot"></span> Приветственный бонус
              </div>
              <div className="bonus-timer">
                Осталось <strong>{formatTime(timeLeft)}</strong>
              </div>
            </div>

            <h2 className="bonus-title">
              Подключите подписку Курс+<br/>
              <span>с приветственным бонусом</span>
            </h2>
            
            <p className="bonus-subtitle">
              Откройте доступ к закрытым курсам платформы, отмеченным меткой Курс+.
            </p>

            <ul className="bonus-list">
              <li>Открывайте программы Курс+.</li>
              <li>Учитесь у экспертов.</li>
              <li>Решайте задачи бизнеса.</li>
            </ul>

            <div className="bonus-warning">
              <strong>Ваш бонус действует ограниченное время</strong>
              <p>Приветственный бонус на подключение Курс+ действует 24 часа после подбора материалов.</p>
            </div>

            {!isAuth ? (
              <>
                <p className="bonus-auth-hint">Войдите в профиль, чтобы активировать приветственный бонус.</p>
                <button className="btn-primary w-100" onClick={handleGoToLogin}>Войти и активировать бонус</button>
              </>
            ) : (
              <>
                <p className="bonus-auth-hint">Бонус будет привязан к вашему аккаунту</p>
                <button className="btn-primary w-100" onClick={handleActivate}>Активировать бонус и подключить Курс+</button>
              </>
            )}

            <button className="bonus-link" onClick={handleClose}>Вернуться к материалам</button>
          </>
        ) : (
          <div className="bonus-success">
            <div className="success-circle">✓</div>
            <h2>Приветственный бонус<br/><span>активирован</span></h2>
            <p>Подписка Курс+ подключена. Теперь вам открыты все курсы и материалы с меткой Курс+.</p>
            <button className="btn-primary w-100" onClick={handleClose}>Перейти к обучению</button>
          </div>
        )}
      </div>
    </div>
  );
};