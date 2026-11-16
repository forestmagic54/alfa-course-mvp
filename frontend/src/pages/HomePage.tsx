// src/pages/HomePage.tsx
import { useState, useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Header } from '../components/Header';
import { MaterialCard } from '../components/MaterialCard';
import { AuthModal } from '../components/AuthModal';
import { BonusModal } from '../components/BonusModal';
import { Onboarding } from '../components/Onboarding';
import { Footer } from '../components/Footer';
import { AuthBanner } from '../components/AuthBanner';
import {
  fetchMaterials,
  fetchRecommendations,
  generateRecommendations,
  generateRoadmap,
  fetchMaterialExplanation,
  submitOnboarding,
  saveRoadmap,
  saveRecommendations,
  fetchOnboarding,
  fetchMyRoadmaps,
  syncAccount,
  activateSubscription,
  clearUserData,
  fetchMaterialDetail, // <-- ДОБАВЛЕН ИМПОРТ
} from '../api';
import './HomePage.css';

const TRAJ_KEY = 'trajectory';
const PERSONAL_KEY = 'personalMaterials';
const PLACEHOLDER = 'Готовим персональное объяснение...';

const isRealId = (id?: string) => !!id && id.length >= 30;

const STAGE_LABELS_UI: Record<string, string> = {
  starting: 'Только запускаю бизнес',
  operating: 'Веду действующий бизнес',
};
const TASK_LABELS_UI: Record<string, string> = {
  sales: 'Увеличить продажи',
  marketing: 'Настроить маркетинг',
  finance: 'Разобраться с финансами',
  management: 'Улучшить управление',
  other: 'Другая задача',
};
const DEPTH_LABELS_UI: Record<string, string> = {
  quick: 'Краткий обзор — только суть',
  practical: 'Подробный разбор — глубокое погружение',
  trajectory: 'Пошаговая траектория — план из 3 этапов',
};

const KIND_DEFAULT: Record<string, string> = {
  course: 'Практический курс для предпринимателей.',
  article: 'Статья с разбором для предпринимателей.',
  document: 'Готовый документ для работы.',
};

const buildDescription = (m: any): string => {
  if (m.description) return m.description;
  const topics = (m.topics || []).map((t: any) => t.title).filter(Boolean);
  const skills = (m.skills || []).map((s: any) => s.title).filter(Boolean);
  const parts: string[] = [];
  if (topics.length) parts.push(`Тема: ${topics.slice(0, 2).join(', ')}.`);
  if (skills.length) parts.push(`Вы освоите: ${skills.slice(0, 3).join(', ')}.`);
  return parts.length ? parts.join(' ') : KIND_DEFAULT[m.kind] || 'Материал для предпринимателей.';
};

const formatMaterial = (material: any, extra: { explanation?: string; lockedText?: string } = {}) => ({
  id: material.id || `material-${Math.random()}`,
  kind: material.kind || 'course',
  title: material.title || 'Без названия',
  description: buildDescription(material),
  duration: material.duration_minutes,
  monetization:
    material.access_type === 'free'
      ? 'free'
      : material.access === 'subscription'
      ? 'subscription'
      : 'paid',
  icon: material.kind === 'course' ? '🎯' : material.kind === 'article' ? '🔍' : '📄',
  explanation: undefined as string | undefined,
  fallbackExplanation: extra.explanation,
  lockedText: extra.lockedText || 'Рекомендация: базовый материал для старта.',
});

export const HomePage = () => {
  const [isAuth, setIsAuth] = useState(!!localStorage.getItem('token'));
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [isBonusModalOpen, setIsBonusModalOpen] = useState(false);
  const [isOnboardingDone, setIsOnboardingDone] = useState(false);
  const [isRetaking, setIsRetaking] = useState(false);
  const [isTrajectory, setIsTrajectory] = useState(false);

  const [isSubscribed, setIsSubscribed] = useState(
    !!localStorage.getItem('token') && localStorage.getItem('subscription') === 'plus'
  );

  const [materials, setMaterials] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const [explanations, setExplanations] = useState<Record<string, string>>({});
  const [failedIds, setFailedIds] = useState<string[]>([]);

  const [activeFilter, setActiveFilter] = useState('all');
  const [viewMode, setViewMode] = useState<'popular' | 'personal'>('popular');

  const wasAuth = useRef(!!localStorage.getItem('token'));

  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    const handleStorageChange = () => setIsAuth(!!localStorage.getItem('token'));
    window.addEventListener('storage', handleStorageChange);
    return () => window.removeEventListener('storage', handleStorageChange);
  }, []);

  useEffect(() => {
    const handleOpenAuth = () => setIsAuthModalOpen(true);
    window.addEventListener('openAuth', handleOpenAuth);
    return () => window.removeEventListener('openAuth', handleOpenAuth);
  }, []);

  const scrollToOnboarding = () => {
    document.getElementById('onboarding-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const scrollToMaterials = () => {
    document.querySelector('.materials-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  useEffect(() => {
    if (location.state?.scrollTo === 'onboarding') {
      setIsRetaking(true);
      setTimeout(scrollToOnboarding, 150);
      navigate(location.pathname, { replace: true, state: {} });
    }
  }, [location]);

  useEffect(() => {
    const savedOnboarding = localStorage.getItem('isOnboardingDone') === 'true';
    const savedTrajectory = localStorage.getItem('isTrajectory') === 'true';
    if (savedOnboarding) {
      setIsOnboardingDone(true);
      setIsTrajectory(savedTrajectory);
    }
  }, []);

  const getFakeData = (personal: boolean) => [
    { id: '1', kind: 'course' as const, title: 'Как выбрать налоговый режим для бизнеса', description: 'Разберитесь, какая система налогообложения подходит именно вашему бизнесу.', duration: 8, monetization: 'free' as const, icon: '📄', explanation: personal ? 'Вы указали эту тему в опросе, поэтому мы рекомендуем этот материал.' : undefined, lockedText: 'Рекомендация: базовый материал для старта.' },
    { id: '2', kind: 'course' as const, title: 'Юридическая самопроверка бизнеса', description: 'Проверьте документы и договоры на соответствие требованиям.', duration: 120, monetization: 'free' as const, icon: '🛡️', explanation: personal ? 'Вы указали эту тему в опросе, поэтому мы рекомендуем этот материал.' : undefined, lockedText: 'Рекомендация: базовый курс по защите сервисов.' },
    { id: '3', kind: 'course' as const, title: 'Управленческий и налоговый учёт', description: 'Настройте прозрачный контроль финансов и отчётности.', duration: 240, monetization: 'subscription' as const, icon: '📈', explanation: personal ? 'Вы указали эту тему в опросе, поэтому мы рекомендуем этот материал.' : undefined, lockedText: 'Рекомендация: базовый курс по финансам.' },
    { id: '4', kind: 'document' as const, title: 'Чек-лист открытия кафе', description: 'PDF · 12 пунктов для старта', duration: null, monetization: 'free' as const, icon: '📄', explanation: personal ? 'Этот чек-лист поможет вам ничего не забыть при открытии кафе.' : undefined, lockedText: 'Рекомендация: чек-лист для старта' },
    { id: '5', kind: 'course' as const, title: 'Где брать клиентов: продвижение в ВКонтакте', description: 'Привлечение клиентов в соцсетях: контент, таргет, блогеры.', duration: 120, monetization: 'free' as const, icon: '🎯', explanation: personal ? 'Вы указали, что хотите увеличить продажи. Этот курс даст вам практические инструменты.' : undefined, lockedText: 'Рекомендация: популярный старт для привлечения клиентов' },
    { id: '6', kind: 'article' as const, title: 'Поисковое продвижение для бизнеса', description: 'Узнайте, как запустить продвижение и привлекать клиентов из поиска.', duration: 8, monetization: 'free' as const, icon: '🔍', explanation: personal ? 'Быстрый способ разобраться, как начать привлекать клиентов через SEO.' : undefined, lockedText: 'Рекомендация: быстрый разбор за 8 минут' },
  ];

  useEffect(() => {
    const loadData = async () => {
      setIsLoading(true);
      let data;

      if (viewMode === 'personal' && isOnboardingDone) {
        const cached = localStorage.getItem(isTrajectory ? TRAJ_KEY : PERSONAL_KEY);
        if (cached) {
          try {
            const parsed = JSON.parse(cached);
            if (Array.isArray(parsed) && parsed.length > 0) {
              setMaterials(parsed);
              setIsLoading(false);
              return;
            }
          } catch {}
        }
        data = await fetchRecommendations();
      } else {
        data = await fetchMaterials(activeFilter === 'all' ? undefined : activeFilter);
      }

      if (data && data.length > 0) {
        // Запрашиваем детали для получения description (его нет в списке каталога)
        const detailedData = await Promise.all(
          data.map(async (item: any) => {
            const material = item.material || item;
            if (!material.description && material.id) {
              const detail = await fetchMaterialDetail(material.id);
              if (detail && detail.description) {
                return { ...material, description: detail.description };
              }
            }
            return material;
          })
        );

        const formatted = detailedData.map((material: any) => {
          const original = data.find((i: any) => (i.material?.id || i.id) === material.id);
          return formatMaterial(material, { explanation: original?.explanation || undefined });
        });
        setMaterials(formatted);
      } else {
        setMaterials(getFakeData(viewMode === 'personal'));
      }
      setIsLoading(false);
    };
    loadData();
  }, [viewMode, isOnboardingDone, isTrajectory, activeFilter, isAuth]);

  const patchCache = (results: Record<string, string>) => {
    [TRAJ_KEY, PERSONAL_KEY].forEach((key) => {
      const raw = localStorage.getItem(key);
      if (!raw) return;
      try {
        const arr = JSON.parse(raw);
        if (!Array.isArray(arr)) return;
        const updated = arr.map((m: any) => (results[m.id] ? { ...m, explanation: results[m.id] } : m));
        localStorage.setItem(key, JSON.stringify(updated));
      } catch {}
    });
  };

  useEffect(() => {
    const loadExplanations = async () => {
      const token = localStorage.getItem('token');
      if (!token || viewMode !== 'personal' || !isOnboardingDone || materials.length === 0) return;

      let answers: any = null;
      try {
        answers = JSON.parse(localStorage.getItem('onboardingAnswers') || 'null');
      } catch {}

      const targets = materials
        .slice(0, 6)
        .filter((m) => isRealId(m.id) && !m.explanation && !explanations[m.id] && !failedIds.includes(m.id));

      if (targets.length === 0) return;

      const responses = await Promise.all(
        targets.map(async (m) => {
          const res = await fetchMaterialExplanation(m.id, token, answers);
          return { id: m.id, text: res?.explanation as string | undefined };
        })
      );

      const results: Record<string, string> = {};
      const failed: string[] = [];
      responses.forEach((r) => {
        if (r.text) results[r.id] = r.text;
        else failed.push(r.id);
      });

      if (Object.keys(results).length > 0) {
        setExplanations((prev) => ({ ...prev, ...results }));
        patchCache(results);
      }
      if (failed.length > 0) setFailedIds((prev) => [...prev, ...failed]);
    };

    loadExplanations();
  }, [materials, viewMode, isOnboardingDone, isAuth]);

  const getExplanation = (m: any): string | undefined => {
    if (viewMode !== 'personal') return undefined;
    if (!isAuth) return undefined;
    if (!isRealId(m.id)) return m.explanation || m.fallbackExplanation;
    if (explanations[m.id]) return explanations[m.id];
    if (m.explanation) return m.explanation;
    if (failedIds.includes(m.id)) return m.fallbackExplanation;
    return PLACEHOLDER;
  };

  const handleOnboardingComplete = async (isTraj: boolean, answers: any, silent: boolean = false) => {
    setIsLoading(true);
    setExplanations({});
    setFailedIds([]);
    const token = localStorage.getItem('token') || undefined;

    if (token) {
      await submitOnboarding(answers);
    }

    let list: any[] = [];
    let roadmapId: string | null = null;
    let recId: string | null = null;

    if (isTraj) {
      const roadmap = await generateRoadmap(answers, token);
      if (roadmap?.steps?.length > 0) {
        roadmapId = roadmap.id || null;
        const steps = [...roadmap.steps].sort((a: any, b: any) => a.position - b.position);
        list = steps.map((step: any) =>
          formatMaterial(step.material, {
            explanation: step.explanation || undefined,
            lockedText: step.transition_text || 'Рекомендация: следующий шаг траектории.',
          })
        );
      }
    }

    if (list.length === 0) {
      const rec = await generateRecommendations(answers, token);
      const items = rec?.items || [];
      if (items.length > 0) {
        recId = rec.id || null;
        list = items.map((item: any) =>
          formatMaterial(item.material || item, { explanation: item.explanation || undefined })
        );
      }
    }

    if (list.length === 0) list = getFakeData(true);

    if (isTraj) list = list.slice(0, 3);

    if (token) {
      if (roadmapId) await saveRoadmap(roadmapId, token);
      if (recId) await saveRecommendations(recId, token);
    }

    localStorage.setItem(isTraj ? TRAJ_KEY : PERSONAL_KEY, JSON.stringify(list));
    localStorage.removeItem(isTraj ? PERSONAL_KEY : TRAJ_KEY);
    localStorage.setItem('isOnboardingDone', 'true');
    localStorage.setItem('isTrajectory', String(isTraj));
    localStorage.setItem('onboardingSynced', token ? 'true' : 'false');

    setMaterials(list);
    setIsTrajectory(isTraj);
    setIsOnboardingDone(true);
    setIsRetaking(false);
    setViewMode('personal');
    setIsLoading(false);

    if (!silent) {
      setTimeout(() => {
        document.getElementById('materials-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 150);
    }
  };

  const hydrateFromAccount = async () => {
    const token = localStorage.getItem('token') || undefined;
    if (!token) return;

    const onboarding = await fetchOnboarding();
    if (!onboarding || onboarding.status !== 'completed' || !onboarding.answers) return;

    const answers = onboarding.answers;
    const isTraj = answers.learning_mode === 'trajectory';

    localStorage.setItem('onboardingAnswers', JSON.stringify(answers));
    localStorage.setItem(
      'onboardingSummary',
      JSON.stringify({
        stage: STAGE_LABELS_UI[answers.business_stage],
        task: TASK_LABELS_UI[answers.current_task],
        depth: DEPTH_LABELS_UI[answers.learning_mode],
      })
    );
    localStorage.setItem('onboardingSynced', 'true');

    let list: any[] = [];

    if (isTraj) {
      const maps = await fetchMyRoadmaps(token);
      const saved = Array.isArray(maps) && maps.length > 0 ? maps[0] : null;
      if (saved?.steps?.length > 0) {
        const steps = [...saved.steps].sort((a: any, b: any) => a.position - b.position);
        list = steps.map((step: any) =>
          formatMaterial(step.material, {
            explanation: step.explanation || undefined,
            lockedText: step.transition_text || 'Рекомендация: следующий шаг траектории.',
          })
        );
      }
    } else {
      const items = await fetchRecommendations();
      if (Array.isArray(items) && items.length > 0) {
        list = items.map((item: any) =>
          formatMaterial(item.material || item, { explanation: item.explanation || undefined })
        );
      }
    }

    if (list.length === 0) {
      await handleOnboardingComplete(isTraj, answers, true);
      return;
    }

    if (isTraj) list = list.slice(0, 3);

    localStorage.setItem(isTraj ? TRAJ_KEY : PERSONAL_KEY, JSON.stringify(list));
    localStorage.removeItem(isTraj ? PERSONAL_KEY : TRAJ_KEY);
    localStorage.setItem('isOnboardingDone', 'true');
    localStorage.setItem('isTrajectory', String(isTraj));

    setExplanations({});
    setFailedIds([]);
    setMaterials(list);
    setIsTrajectory(isTraj);
    setIsOnboardingDone(true);
    setIsRetaking(false);
  };

  const resetLocalState = () => {
    setIsOnboardingDone(false);
    setIsTrajectory(false);
    setIsRetaking(false);
    setExplanations({});
    setFailedIds([]);
    setViewMode('popular');
  };

  useEffect(() => {
    if (!isAuth) {
      localStorage.removeItem('subscription');
      setIsSubscribed(false);
      if (wasAuth.current || localStorage.getItem('accountId')) {
        clearUserData();
        resetLocalState();
      }
      wasAuth.current = false;
      return;
    }

    wasAuth.current = true;
    let cancelled = false;

    (async () => {
      const info = await syncAccount();
      if (cancelled) return;

      if (!info) {
        setIsAuth(!!localStorage.getItem('token'));
        return;
      }

      setIsSubscribed(info.subscribed);
      if (info.switched) resetLocalState();

      const localDone = localStorage.getItem('isOnboardingDone') === 'true';

      if (info.me.onboarding_completed) {
        if (info.switched || !localDone) await hydrateFromAccount();
      } else {
        let answers: any = null;
        try {
          answers = JSON.parse(localStorage.getItem('onboardingAnswers') || 'null');
        } catch {}
        if (answers && localDone && localStorage.getItem('onboardingSynced') !== 'true') {
          await handleOnboardingComplete(localStorage.getItem('isTrajectory') === 'true', answers, true);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [isAuth]);

  const handleBonusActivated = async () => {
    const active = await activateSubscription();
    setIsSubscribed(active);
  };

  const handleRetake = () => {
    setIsRetaking(true);
    setTimeout(scrollToOnboarding, 100);
  };

  const handleShowResults = () => {
    setViewMode('personal');
    setTimeout(() => {
      document.getElementById('materials-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
  };

  const closeAuthModal = () => {
    setIsAuthModalOpen(false);
    setIsAuth(!!localStorage.getItem('token'));
  };

  const GuestCta = () =>
    !isAuth && viewMode === 'personal' && isOnboardingDone ? (
      <button
        className="btn-outline-small"
        onClick={() => setIsAuthModalOpen(true)}
        style={{ alignSelf: 'flex-start', marginTop: '10px' }}
      >
        🔒 Узнать, почему это подходит именно вам — зарегистрируйтесь
      </button>
    ) : null;

  return (
    <div className="home-page">
      <Header isAuth={isAuth} onLoginClick={() => setIsAuthModalOpen(true)} />
      <main className="main-content">
        <section className="hero-section">
          <div className="hero-left">
            <div className="hero-badge">✦ Персональные рекомендации</div>
            <h1 className="hero-title">Альфа-Курс: умные траектории роста</h1>
            <p className="hero-subtitle">Персональный подбор курсов, статей и полезных документов для вашего бизнеса</p>
            <button className="btn-primary" onClick={scrollToOnboarding}>Подобрать материалы →</button>
            <div style={{ marginTop: '16px', cursor: 'pointer', color: '#666', fontSize: '15px', fontWeight: '500', paddingLeft: '24px' }} onClick={scrollToMaterials}>Перейти к популярному →</div>
          </div>
          <div className="hero-right">
            <div className="hero-bg-circle"></div>
            <div className="hero-red-card"><div className="hero-red-card-inner"></div></div>
            <div className="hero-white-card">
              <div className="hero-white-card-header"><span>Траектория роста</span><div className="hero-chart-icon">↗</div></div>
              <div className="hero-chart-value">+32%</div>
              <div className="hero-chart-bars">
                <div className="bar" style={{ height: '20%' }}></div>
                <div className="bar" style={{ height: '40%' }}></div>
                <div className="bar" style={{ height: '35%' }}></div>
                <div className="bar" style={{ height: '60%' }}></div>
                <div className="bar" style={{ height: '50%' }}></div>
                <div className="bar" style={{ height: '80%' }}></div>
                <div className="bar" style={{ height: '100%', backgroundColor: 'var(--alpha-red)' }}></div>
              </div>
            </div>
            <div className="hero-bottom-badge">
              <div className="badge-icon">💡</div>
              <div><div className="badge-sub">Следующий шаг</div><div className="badge-title">Расти системно</div></div>
            </div>
          </div>
        </section>

        <section className="features-section">
          <div className="feature-item"><div className="feature-icon">⚡</div><div className="feature-text"><strong>Умный подбор</strong><span>курсов</span></div></div>
          <div className="feature-item"><div className="feature-icon">📈</div><div className="feature-text"><strong>Реальные инструменты</strong><span>для роста бизнеса</span></div></div>
          <div className="feature-item"><div className="feature-icon">⭐</div><div className="feature-text"><strong>Эксперты</strong><span>Альфа Банка</span></div></div>
          <div className="feature-item"><div className="feature-icon">❤️</div><div className="feature-text"><strong>Обучение в удобном</strong><span>формате</span></div></div>
        </section>

        <section className="how-it-works">
          <div className="how-left">
            <span className="how-badge">Как это работает?</span>
            <h2>Просто. Персонально.<br/>Эффективно.</h2>
            <p>Пройдите короткий опрос о вашем бизнесе или зарегистрируйтесь и получите индивидуальную траекторию развития.</p>
          </div>
          <div className="how-right">
            <div className="how-step"><div className="step-header"><span className="step-circle">1</span><h4>Расскажите о своём бизнесе</h4></div><p>Укажите сферу, стадию развития и цели</p><div className="step-icon">💼</div></div>
            <div className="step-arrow-right">→</div>
            <div className="how-step"><div className="step-header"><span className="step-circle">2</span><h4>Получите рекомендации</h4></div><p>Мы подберём курсы под ваши задачи</p><div className="step-icon">🎓</div></div>
            <div className="step-arrow-right">→</div>
            <div className="how-step"><div className="step-header"><span className="step-circle">3</span><h4>Развивайте бизнес</h4></div><p>Следуйте плану и отслеживайте прогресс</p><div className="step-icon">📈</div></div>
          </div>
        </section>

        <Onboarding
          onComplete={(isTraj, answers) => handleOnboardingComplete(isTraj, answers)}
          isDone={isOnboardingDone && !isRetaking}
          onRetake={handleRetake}
          onShowResults={handleShowResults}
        />

        <section className="materials-section" id="materials-section" style={{ scrollMarginTop: '100px' }}>
          <div className="materials-header-top">
            <span className="badge">Знания для бизнеса</span>
            <h2>{viewMode === 'personal' ? 'Персональная подборка для вашего бизнеса' : 'Материалы, которые выбирают предприниматели'}</h2>
            <p>{viewMode === 'personal' ? 'Подобрано специально под ваши задачи и цели' : 'Практические инструменты, которые можно применять сразу.'}</p>
          </div>

          <div className="materials-controls">
            <div className="toggles">
              <button className={`toggle-btn ${viewMode === 'popular' ? 'active' : ''}`} onClick={() => setViewMode('popular')}>По популярности</button>
              <button className={`toggle-btn ${viewMode === 'personal' ? 'active' : ''}`} onClick={() => {
                const isDone = localStorage.getItem('isOnboardingDone') === 'true';
                if (isDone) setViewMode('personal');
                else scrollToOnboarding();
              }}>Персональный подбор</button>
            </div>
            {viewMode === 'personal' && isOnboardingDone && !isSubscribed && (
              <button className="btn-bonus" onClick={() => setIsBonusModalOpen(true)}>Активировать бонус</button>
            )}
          </div>

          <div className="materials-chips">
            <button className={`chip ${activeFilter === 'all' ? 'active' : ''}`} onClick={() => setActiveFilter('all')}>Все</button>
            <button className={`chip ${activeFilter === 'course' ? 'active' : ''}`} onClick={() => setActiveFilter('course')}>Курсы</button>
            <button className={`chip ${activeFilter === 'article' ? 'active' : ''}`} onClick={() => setActiveFilter('article')}>Статьи</button>
            <button className={`chip ${activeFilter === 'document' ? 'active' : ''}`} onClick={() => setActiveFilter('document')}>Документы</button>
          </div>

          {!isAuth && viewMode === 'personal' && isOnboardingDone && (
            <AuthBanner variant={isTrajectory ? 'trajectory' : 'personal'} onLoginClick={() => setIsAuthModalOpen(true)} />
          )}

          {isLoading ? (
            <div style={{ textAlign: 'center', padding: '40px' }}>Загрузка материалов...</div>
          ) : isTrajectory && viewMode === 'personal' ? (
            <div className="trajectory-wrapper">
              <div className="trajectory-header">
                <h3>Ваша траектория обучения</h3>
                <p>3 шага, чтобы достичь вашей цели</p>
              </div>
              <div className="trajectory-steps">
                {materials.slice(0, 3).map((m, index) => {
                  const stepTexts = [
                    'Точка входа: базовый материал для старта. Разбор под ваш бизнес — после входа.',
                    'Следующий этап: переход к практике и проверке договоров. Детали — после входа.',
                    'Закрепление: системный контроль отчётности. Персональный план — после входа.',
                  ];
                  return (
                    <div key={m.id} className="trajectory-step-card">
                      <MaterialCard
                        {...m}
                        explanation={getExplanation(m)}
                        isAuth={isAuth}
                        isOnboardingDone={isOnboardingDone}
                        lockedText={m.lockedText || stepTexts[index]}
                        stepNumber={index + 1}
                      />
                      <GuestCta />
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="materials-grid">
              {materials.map((m) => (
                <div key={m.id} style={{ display: 'flex', flexDirection: 'column' }}>
                  <MaterialCard
                    {...m}
                    explanation={getExplanation(m)}
                    isAuth={isAuth}
                    isOnboardingDone={isOnboardingDone}
                    lockedText={m.lockedText}
                  />
                  <GuestCta />
                </div>
              ))}
            </div>
          )}
        </section>
      </main>
      <Footer onRecommendationsClick={() => {}} />
      <AuthModal isOpen={isAuthModalOpen} onClose={closeAuthModal} />
      <BonusModal
        isOpen={isBonusModalOpen}
        onClose={() => setIsBonusModalOpen(false)}
        isAuth={isAuth}
        onLoginClick={() => setIsAuthModalOpen(true)}
        onBonusActivated={handleBonusActivated}
      />
    </div>
  );
};