import './SuccessModal.css';

interface SuccessModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const SuccessModal = ({ isOpen, onClose }: SuccessModalProps) => {
  if (!isOpen) return null;

  return (
    <div className="success-overlay" onClick={onClose}>
      <div className="success-modal" onClick={(e) => e.stopPropagation()}>
        <div className="success-icon">✅</div>
        <h2>Курс приобретён!</h2>
        <p>Доступ к материалам открыт. Вы можете начать обучение прямо сейчас.</p>
        <button className="btn-primary w-100" onClick={onClose}>Перейти к обучению →</button>
      </div>
    </div>
  );
};