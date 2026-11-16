// src/pages/ProfilePage.tsx
import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Header } from '../components/Header';
import { Footer } from '../components/Footer';
import { BonusModal } from '../components/BonusModal';
import { fetchMyRoadmaps } from '../api';
import './ProfilePage.css';

const STAGE_LABELS: Record<string, string> = {
  starting: 'Запуск бизнеса',
  operating: 'Бизнес уже работает',
};

const TASK_LABELS: Record<string, string> = {
  sales: 'Продажи',
  marketing: 'Маркетинг',
  finance: 'Финансы и учёт',
  management: 'Управление',
  other: 'Другая задача',
};

const KIND_LABELS: Record<string, string> = {
  course: '🎓 Курс',
  article: '📄 Статья',
  document: '📄 Документ',
};

const readJSON = (key: string, fallback: any) => {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
};

export const ProfilePage = () => {
  const navigate = useNavigate();

  const [isCompletedOpen, setIsCompletedOpen] = useState(false);
  const [isBonusModalOpen, setIsBonusModalOpen] = useState(false);

  const [isSubscribed, setIsSubscribed] = useState(localStorage.getItem('subscription') === 'plus');

  const [completedMaterials, setCompletedMaterials] = useState<any[]>([]);
  const [favoriteMaterials, setFavoriteMaterials] = useState<any[]>([]);
  const [trajectory, setTrajectory] = useState<any[]>([]);
  const [recommendations, setRecommendations] = useState<any[]>([]);
  const [answers, setAnswers] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);

  const [activeSavedFilter, setActiveSavedFilter] = useState('all');

  const handleBonusActivated = () => {
    setIsSubscribed(true);
    localStorage.setItem('subscription', 'plus');
  };

  useEffect(() => {
    const loadProfileData = async () => {
      // 1. Пройденные материалы
      setCompletedMaterials(readJSON('completedMaterials', []));

      // 2. Ответы анкеты (для бизнес-профиля)
      setAnswers(readJSON('onboardingAnswers', null));

      // 3. Избранное
      const favIds: string[] = readJSON('favorites', []);
      if (favIds.length > 0) {
        try {
          const favData = await Promise.all(
            favIds.map(async (id) => {
              const res = await fetch(`/api/v1/materials/${id}`);
              if (res.ok) return await res.json();
              return null;
            })
          );
          setFavoriteMaterials(favData.filter(Boolean));
        } catch (error) {
          console.error('Ошибка загрузки избранного:', error);
        }
      }

      // 4. Результат анкеты с главной: траектория или персональная подборка
      const localTraj: any[] = readJSON('trajectory', []);
      const localRec: any[] = readJSON('personalMaterials', []);
      setRecommendations(Array.isArray(localRec) ? localRec : []);

      // 5. Для вошедшего пользователя подтягиваем отметки «изучено» с бэкенда
      const token = localStorage.getItem('token');
      let backendRoadmaps: any[] = [];
      if (token) {
        const res = await fetchMyRoadmaps(token);
        if (Array.isArray(res)) backendRoadmaps = res;
      }

      const studiedIds = new Set<string>();
      backendRoadmaps.forEach((r: any) =>
        r.steps?.forEach((s: any) => {
          if (s.is_studied) studiedIds.add(s.material.id);
        })
      );

      if (Array.isArray(localTraj) && localTraj.length > 0) {
        setTrajectory(localTraj.map((s: any) => ({ ...s, is_studied: studiedIds.has(s.id) })));
      } else if (backendRoadmaps.length > 0 && localRec.length === 0) {
        // Запасной вариант: карта сохранена на бэкенде, локально её нет (другое устройство)
        const steps = [...backendRoadmaps[0].steps]
          .sort((a: any, b: any) => a.position - b.position)
          .map((step: any) => ({
            id: step.material.id,
            kind: step.material.kind,
            title: step.material.title,
            duration: step.material.duration_minutes,
            is_studied: step.is_studied,
            explanation: step.explanation,
            lockedText: step.transition_text,
          }));
        setTrajectory(steps);
      }

      setIsLoading(false);
    };

    loadProfileData();
  }, []);

  const isStepDone = (step: any) =>
    completedMaterials.some((m: any) => m.id === step.id) || step.is_studied;

  const completedSteps = trajectory.filter(isStepDone).length;
  const progress = trajectory.length > 0 ? Math.round((completedSteps / trajectory.length) * 100) : 0;
  const nextStep = trajectory.find((step: any) => !isStepDone(step));

  const filteredSavedMaterials = favoriteMaterials.filter((item) => {
    if (activeSavedFilter === 'all') return true;
    return item.kind === activeSavedFilter;
  });

  const profileTags = answers
    ? [
        STAGE_LABELS[answers.business_stage] && `Стадия: ${STAGE_LABELS[answers.business_stage]}`,
        TASK_LABELS[answers.current_task] && `Задача: ${TASK_LABELS[answers.current_task]}`,
      ].filter(Boolean) as string[]
    : [];

  if (isLoading) {
    return <div style={{ textAlign: 'center', padding: '100px' }}>Загрузка профиля...</div>;
  }

  return (
    <div className="profile-page">
      <Header isAuth={true} onLoginClick={() => {}} />

      <main className="profile-content">
        <div className="profile-header">
          <div>
            <h1>Личный кабинет</h1>
            <p className="profile-subtitle-text">Всё для следующего шага в вашем бизнесе</p>
          </div>
          <Link to="/" className="btn-back-home">
            На главную <span>↗</span>
          </Link>
        </div>

        <div className="profile-top-cards">
          <div className="profile-card profile-card--business">
            <div className="card-icon">💼</div>
            <div className="card-content">
              <h3>Ваш бизнес-профиль</h3>
              <p className="profile-tags">
                {profileTags.length > 0
                  ? profileTags.map((t, i) => (
                      <span key={i}>
                        {i > 0 && <span> • </span>}
                        {t}
                      </span>
                    ))
                  : 'Анкета пока не пройдена'}
              </p>
              <button
                className="btn-outline-small"
                onClick={() => navigate('/', { state: { scrollTo: 'onboarding' } })}
              >
                {answers ? 'Изменить параметры' : 'Пройти анкету'}
              </button>
            </div>
          </div>

          <div className="profile-card profile-card--subscription">
            <div className="subscription-left">
              <h3>Ваша подписка</h3>
              <div className="subscription-status">
                {isSubscribed ? (
                  <>
                    <strong>Курс+</strong> <span className="badge-free" style={{ background: '#ffe5e5', color: '#d32f2f' }}>Активна</span>
                  </>
                ) : (
                  <>
                    <strong>Базовый</strong> <span className="badge-free">Бесплатно</span>
                  </>
                )}
              </div>
              <p className="subscription-desc">
                {isSubscribed
                  ? 'Все курсы и материалы с меткой Курс+ открыты для вас.'
                  : 'Больше возможностей для роста с Курс+. Материалы, инструменты и обучение без ограничений'}
              </p>
            </div>
            <div className="subscription-right">
              {isSubscribed ? (
                <button className="btn-primary" disabled style={{ opacity: 0.5, cursor: 'default' }}>
                  Подписка активна
                </button>
              ) : (
                <button className="btn-primary" onClick={() => setIsBonusModalOpen(true)}>
                  Активировать бонус
                </button>
              )}
              <div className="subscription-price">990 ₽ / месяц</div>
            </div>
          </div>
        </div>

        <div className="section-header-row">
          <h2>Мои траектории развития</h2>
          <span className="section-count">{trajectory.length > 0 ? '1 траектория' : '0 траекторий'}</span>
        </div>

        {/* ТРАЕКТОРИЯ: появляется после прохождения анкеты */}
        {trajectory.length > 0 ? (
          <div className="trajectories-grid">
            <div className="trajectory-card trajectory-card--active">
              <div className="trajectory-header">
                <div className="trajectory-title">
                  <span className="trajectory-icon">📄</span>
                  <h4>Ваша персональная траектория</h4>
                </div>
                <span className="trajectory-percent">{progress}%</span>
              </div>
              <p className="trajectory-progress-text">{completedSteps} из {trajectory.length} шагов пройдено</p>
              <div className="progress-bar">
                <div style={{ width: `${progress}%` }}></div>
              </div>

              {/* Список шагов */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', margin: '20px 0' }}>
                {trajectory.map((step: any, index: number) => {
                  const done = isStepDone(step);
                  return (
                    <div
                      key={step.id}
                      onClick={() => navigate(`/material/${step.id}`)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '12px',
                        padding: '12px 14px',
                        borderRadius: '14px',
                        background: done ? '#f1faf3' : '#fafafa',
                        border: '1px solid #eee',
                        cursor: 'pointer',
                      }}
                    >
                      <span
                        style={{
                          minWidth: '28px',
                          height: '28px',
                          borderRadius: '50%',
                          background: done ? '#2e9e4f' : '#dd4433',
                          color: '#fff',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontSize: '14px',
                          fontWeight: 600,
                        }}
                      >
                        {done ? '✓' : index + 1}
                      </span>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 600 }}>{step.title}</div>
                        <div style={{ fontSize: '13px', color: '#777' }}>
                          {KIND_LABELS[step.kind] || 'Материал'}
                          {step.duration ? ` · ${step.duration} мин` : ''}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="trajectory-footer">
                <div>
                  <span className="trajectory-step-label">Следующий шаг</span>
                  <p className="trajectory-step-name">{nextStep?.title || 'Все шаги пройдены!'}</p>
                </div>
                {nextStep && (
                  <button
                    className="btn-primary-small"
                    onClick={() => navigate(`/material/${nextStep.id}`)}
                  >
                    Продолжить обучение →
                  </button>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="empty-trajectory" style={{ padding: '40px', background: '#fff', borderRadius: '24px', textAlign: 'center', marginBottom: '48px' }}>
            <h3 style={{ fontSize: '20px', marginBottom: '12px' }}>У вас пока нет активной траектории</h3>
            <p style={{ color: '#666', marginBottom: '24px' }}>Ответьте на 3 вопроса о вашем бизнесе — система подберёт 3 подходящих материала и выстроит их в последовательный план под вашу задачу.</p>
            <button className="btn-primary" onClick={() => navigate('/', { state: { scrollTo: 'onboarding' } })}>
              Составить траекторию →
            </button>
          </div>
        )}

        {/* ПЕРСОНАЛЬНАЯ ПОДБОРКА: если в анкете выбран не режим «траектория» */}
        {recommendations.length > 0 && (
          <>
            <div className="section-header-row">
              <h2>Моя персональная подборка</h2>
              <span className="section-subtext">Подобрано по вашей анкете</span>
            </div>
            <div className="saved-materials-grid" style={{ marginBottom: '48px' }}>
              {recommendations.map((item: any) => (
                <div
                  key={item.id}
                  className="saved-card"
                  onClick={() => navigate(`/material/${item.id}`)}
                  style={{ cursor: 'pointer' }}
                >
                  <div className="saved-card-header">
                    <span className="saved-type">{KIND_LABELS[item.kind] || '📄 Материал'}</span>
                  </div>
                  <h4>{item.title}</h4>
                  <p className="saved-meta">{item.duration ? `${item.duration} мин` : 'Материал'}</p>
                  {item.explanation && item.explanation !== 'Загрузка персонального объяснения...' && (
                    <p style={{ fontSize: '13px', color: '#666', marginTop: '8px' }}>{item.explanation}</p>
                  )}
                </div>
              ))}
            </div>
          </>
        )}

        <div className="section-header-row">
          <h2>Сохранённые инструменты</h2>
          <span className="section-subtext">Всё нужное — под рукой</span>
        </div>

        <div className="filters-row">
          <button className={`chip ${activeSavedFilter === 'all' ? 'active' : ''}`} onClick={() => setActiveSavedFilter('all')}>
            Все · {favoriteMaterials.length}
          </button>
          <button className={`chip ${activeSavedFilter === 'course' ? 'active' : ''}`} onClick={() => setActiveSavedFilter('course')}>
            Курсы · {favoriteMaterials.filter((m) => m.kind === 'course').length}
          </button>
          <button className={`chip ${activeSavedFilter === 'article' ? 'active' : ''}`} onClick={() => setActiveSavedFilter('article')}>
            Статьи · {favoriteMaterials.filter((m) => m.kind === 'article').length}
          </button>
          <button className={`chip ${activeSavedFilter === 'document' ? 'active' : ''}`} onClick={() => setActiveSavedFilter('document')}>
            Документы · {favoriteMaterials.filter((m) => m.kind === 'document').length}
          </button>
        </div>

        <div className="saved-materials-grid">
          {filteredSavedMaterials.length > 0 ? (
            filteredSavedMaterials.map((item) => (
              <div
                key={item.id}
                className="saved-card"
                onClick={() => navigate(`/material/${item.id}`)}
                style={{ cursor: 'pointer' }}
              >
                <div className="saved-card-header">
                  <span className="saved-type">
                    {item.kind === 'course' ? '🎓 Курс' : item.kind === 'article' ? '📄 Статья' : '📄 Документ'}
                  </span>
                  <span className="bookmark active">🔖</span>
                </div>
                <h4>{item.title}</h4>
                <p className="saved-meta">{item.duration_minutes ? `${item.duration_minutes} мин` : 'Материал'}</p>
              </div>
            ))
          ) : (
            <p style={{ color: '#666', gridColumn: '1 / -1' }}>У вас пока нет сохранённых материалов.</p>
          )}
        </div>

        <div className="accordion">
          <button
            className={`accordion-header ${isCompletedOpen ? 'open' : ''}`}
            onClick={() => setIsCompletedOpen(!isCompletedOpen)}
          >
            <div className="accordion-title">
              <span>🕒</span> Пройденные материалы ({completedMaterials.length})
            </div>
            <span className="accordion-arrow">{isCompletedOpen ? '▲' : '▼'}</span>
          </button>

          {isCompletedOpen && (
            <div className="accordion-body">
              {completedMaterials.length > 0 ? (
                <div className="completed-list">
                  {completedMaterials.map((m, index) => (
                    <div
                      key={index}
                      className="completed-item"
                      onClick={() => navigate(`/material/${m.id}`)}
                      style={{ cursor: 'pointer' }}
                    >
                      <div>
                        <span className="completed-type">{m.type}</span>
                        <h4>{m.title}</h4>
                      </div>
                      <div className="completed-right">
                        <span className="completed-date">{m.date}</span>
                        <span className="completed-check">✓ Пройдено</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p>Вы пока не отметили ни одного материала как пройденный.</p>
              )}
            </div>
          )}
        </div>
      </main>

      <Footer />

      <BonusModal
        isOpen={isBonusModalOpen}
        onClose={() => setIsBonusModalOpen(false)}
        isAuth={true}
        onLoginClick={() => {}}
        onBonusActivated={handleBonusActivated}
      />
    </div>
  );
};