// src/components/Onboarding.tsx
import { useState } from 'react';
import './Onboarding.css';

interface OnboardingProps {
  onComplete: (isTrajectory: boolean, answers: any) => void;
  isDone: boolean;            // анкета пройдена -> показываем свёрнутую плашку
  onRetake: () => void;       // нажали «Пройти заново»
  onShowResults: () => void;  // нажали «К подборке»
}

// ui — что хранится в форме, api — что уходит на бэкенд (коды из GET /onboarding/questionnaire)
const STAGE_OPTIONS = [
  { ui: 'starting', api: 'starting', label: 'Только запускаю бизнес' },
  { ui: 'active', api: 'operating', label: 'Веду действующий бизнес' },
  { ui: 'scale', api: 'operating', label: 'Масштабирую бизнес' },
];

const TASK_OPTIONS = [
  { ui: 'sales', api: 'sales', label: 'Увеличить продажи' },
  { ui: 'marketing', api: 'marketing', label: 'Настроить маркетинг' },
  { ui: 'finance', api: 'finance', label: 'Разобраться с финансами' },
];

const DEPTH_OPTIONS = [
  { ui: 'brief', api: 'quick', label: 'Краткий обзор — только суть' },
  { ui: 'detailed', api: 'practical', label: 'Подробный разбор — глубокое погружение' },
  { ui: 'trajectory', api: 'trajectory', label: 'Пошаговая траектория — план из 3 этапов' },
];

const readSummary = (): { stage?: string; task?: string; depth?: string } => {
  try {
    return JSON.parse(localStorage.getItem('onboardingSummary') || '{}');
  } catch {
    return {};
  }
};

export const Onboarding = ({ onComplete, isDone, onRetake, onShowResults }: OnboardingProps) => {
  const [step, setStep] = useState(1);

  const [stage, setStage] = useState('');
  const [task, setTask] = useState('');
  const [depth, setDepth] = useState('');

  const nextStep = () => setStep((prev) => Math.min(prev + 1, 3));
  const prevStep = () => setStep((prev) => Math.max(prev - 1, 1));

  const isStepValid = () => {
    if (step === 1) return stage !== '';
    if (step === 2) return task !== '';
    if (step === 3) return depth !== '';
    return false;
  };

  const handleComplete = () => {
    const stageOpt = STAGE_OPTIONS.find((o) => o.ui === stage);
    const taskOpt = TASK_OPTIONS.find((o) => o.ui === task);
    const depthOpt = DEPTH_OPTIONS.find((o) => o.ui === depth);

    const answers = {
      business_stage: stageOpt?.api,
      current_task: taskOpt?.api,
      learning_mode: depthOpt?.api,
    };

    // Сохраняем для личного кабинета и для свёрнутой плашки
    localStorage.setItem('onboardingAnswers', JSON.stringify(answers));
    localStorage.setItem(
      'onboardingSummary',
      JSON.stringify({ stage: stageOpt?.label, task: taskOpt?.label, depth: depthOpt?.label })
    );

    onComplete(depth === 'trajectory', answers);
  };

  const handleRetake = () => {
    setStep(1);
    setStage('');
    setTask('');
    setDepth('');
    onRetake();
  };

  const renderOptions = (
    options: { ui: string; label: string }[],
    name: string,
    value: string,
    setValue: (v: string) => void
  ) =>
    options.map((o) => (
      <label key={o.ui} className={`option ${value === o.ui ? 'selected' : ''}`}>
        <input
          type="radio"
          name={name}
          value={o.ui}
          checked={value === o.ui}
          onChange={(e) => setValue(e.target.value)}
        />{' '}
        {o.label}
      </label>
    ));

  // ===== СВЁРНУТОЕ СОСТОЯНИЕ: анкета пройдена =====
  if (isDone) {
    const summary = readSummary();
    const rows = [
      { title: 'Этап бизнеса', value: summary.stage },
      { title: 'Задача', value: summary.task },
      { title: 'Формат обучения', value: summary.depth },
    ].filter((r) => r.value);

    return (
      <section
        className="onboarding-wrapper"
        id="onboarding-section"
        style={{ scrollMarginTop: '100px' }}
      >
        <div className="onboarding-left">
          <span className="badge">Персональный маршрут</span>
          <h2>Анкета пройдена</h2>
          <p>Мы подобрали материалы под ваши ответы. Если задачи изменились, пройдите анкету заново.</p>
        </div>

        <div className="onboarding-card">
          <div className="card-header">
            <h3>✓ Ваши ответы сохранены</h3>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', margin: '8px 0 24px' }}>
            {rows.map((r) => (
              <div key={r.title} style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                <span style={{ fontSize: '13px', color: '#888' }}>{r.title}</span>
                <span style={{ fontSize: '16px', fontWeight: 500 }}>{r.value}</span>
              </div>
            ))}
          </div>

          <div className="card-actions" style={{ justifyContent: 'flex-end' }}>
            <div className="nav-btns">
              <button className="btn-back" onClick={handleRetake}>Пройти заново</button>
              <button className="btn-next" onClick={onShowResults}>К подборке →</button>
            </div>
          </div>
        </div>
      </section>
    );
  }

  // ===== ФОРМА =====
  return (
    <section
      className="onboarding-wrapper"
      id="onboarding-section"
      style={{ scrollMarginTop: '100px' }}
    >
      <div className="onboarding-left">
        <span className="badge">Персональный маршрут</span>
        <h2>Настроим обучение под вас.</h2>
        <p>Ответьте на несколько вопросов, чтобы мы могли составить для вас персональный план</p>
      </div>

      <div className="onboarding-card">
        <div className="card-header">
          <h3>
            {step === 1 && 'На каком этапе ваш бизнес?'}
            {step === 2 && 'Какую задачу хотите решить?'}
            {step === 3 && 'Насколько глубоко хотите изучить тему?'}
          </h3>
          <span className="step-counter">Шаг {step} из 3</span>
        </div>

        <div className="progress-bar">
          <div className="progress-fill" style={{ width: `${(step / 3) * 100}%` }}></div>
        </div>

        <div className="options-list">
          {step === 1 && (
            <>
              {renderOptions(STAGE_OPTIONS, 'stage', stage, setStage)}

              <div className="select-wrapper">
                <select className="option-select" defaultValue="">
                  <option value="" disabled>Сфера бизнеса (необязательно)</option>
                  <option value="b2b">B2B</option>
                  <option value="b2g">B2G</option>
                  <option value="ecom">ECom</option>
                  <option value="horeca">HoReCa</option>
                  <option value="accounting">Бухгалтерия</option>
                  <option value="wholesale">Оптовая торговля</option>
                  <option value="manufacturing">Производство</option>
                  <option value="retail">Розница</option>
                  <option value="construction">Строительство и недвижимость</option>
                  <option value="transport">Транспорт и логистика</option>
                  <option value="services">Услуги</option>
                </select>
              </div>
            </>
          )}
          {step === 2 && renderOptions(TASK_OPTIONS, 'task', task, setTask)}
          {step === 3 && renderOptions(DEPTH_OPTIONS, 'depth', depth, setDepth)}
        </div>

        <div className="card-actions" style={{ justifyContent: 'flex-end' }}>
          <div className="nav-btns">
            {step > 1 && <button className="btn-back" onClick={prevStep}>Назад</button>}

            {step < 3 ? (
              <button
                className={`btn-next ${!isStepValid() ? 'disabled' : ''}`}
                onClick={nextStep}
                disabled={!isStepValid()}
              >
                Далее →
              </button>
            ) : (
              <button
                className={`btn-next ${!isStepValid() ? 'disabled' : ''}`}
                onClick={handleComplete}
                disabled={!isStepValid()}
              >
                Получить подборку →
              </button>
            )}
          </div>
        </div>
      </div>
    </section>
  );
};