// src/pages/MaterialPage.tsx
import { useState, useEffect } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Header } from '../components/Header';
import { SuccessModal } from '../components/SuccessModal';
import { Footer } from '../components/Footer';
import { AuthModal } from '../components/AuthModal';
import { MaterialCard } from '../components/MaterialCard';
import { purchaseCourse, markAsCompleted, fetchMaterialExplanation } from '../api';
import './MaterialPage.css';

export const MaterialPage = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  
  // Берем токен из localStorage
  const token = localStorage.getItem('token') || undefined;
  const isAuth = !!token;

  const [course, setCourse] = useState<any>(null);
  const [relatedMaterials, setRelatedMaterials] = useState<any[]>([]);
  const [aiExplanation, setAiExplanation] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const [isSuccessOpen, setIsSuccessOpen] = useState(false);
  const [isFavorite, setIsFavorite] = useState(false);
  const [showToast, setShowToast] = useState(false);
  const [isCompleted, setIsCompleted] = useState(false);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);

  useEffect(() => {
    const loadCourse = async () => {
      if (!id) return;
      
      const favorites = JSON.parse(localStorage.getItem('favorites') || '[]');
      const completed = JSON.parse(localStorage.getItem('completedMaterials') || '[]');
      
      setIsFavorite(favorites.includes(id));
      setIsCompleted(completed.some((m: any) => m.id === id));

      try {
        const response = await fetch(`/api/v1/materials/${id}`);
        if (!response.ok) throw new Error('Ошибка загрузки курса');
        
        const data = await response.json();
        setCourse(data);
        setRelatedMaterials(data.related_materials || []);

        // Если авторизован и есть токен — запрашиваем объяснение от ИИ
        if (isAuth && token) {
          const explanationData = await fetchMaterialExplanation(id, token);
          if (explanationData?.explanation) {
            setAiExplanation(explanationData.explanation);
          }
        }
      } catch (error) {
        console.error("Ошибка:", error);
      } finally {
        setIsLoading(false);
      }
    };

    loadCourse();
  }, [id, isAuth, token]);

  const handleFavoriteClick = () => {
    if (!isAuth) {
      setIsAuthModalOpen(true);
      return;
    }
    
    const newState = !isFavorite;
    setIsFavorite(newState);
    
    let favorites = JSON.parse(localStorage.getItem('favorites') || '[]');
    if (newState) {
      if (!favorites.includes(id)) favorites.push(id);
    } else {
      favorites = favorites.filter((favId: string) => favId !== id);
    }
    localStorage.setItem('favorites', JSON.stringify(favorites));

    if (newState) {
      setShowToast(true);
      setTimeout(() => setShowToast(false), 3000);
    }
  };

  const handleCompleteClick = async () => {
    if (!isAuth) {
      setIsAuthModalOpen(true);
      return;
    }
    
    const newState = !isCompleted;
    setIsCompleted(newState);

    if (newState && id) {
      await markAsCompleted(id);
      const completedList = JSON.parse(localStorage.getItem('completedMaterials') || '[]');
      if (!completedList.find((m: any) => m.id === id)) {
        completedList.push({
          id: id,
          title: course?.title || 'Курс',
          type: course?.kind === 'course' ? 'Курс' : 'Статья',
          date: new Date().toLocaleDateString('ru-RU')
        });
        localStorage.setItem('completedMaterials', JSON.stringify(completedList));
      }
    } else if (!newState && id) {
      const completedList = JSON.parse(localStorage.getItem('completedMaterials') || '[]');
      const filtered = completedList.filter((m: any) => m.id !== id);
      localStorage.setItem('completedMaterials', JSON.stringify(filtered));
    }
  };

  const handleBuyClick = async () => {
    if (id) {
      await purchaseCourse(id);
      setIsSuccessOpen(true);
    }
  };

  const handleGoToOnboarding = () => {
    navigate('/', { state: { scrollTo: 'onboarding' } });
  };

  if (isLoading) {
    return <div style={{ textAlign: 'center', padding: '100px', fontSize: '20px' }}>Загрузка курса...</div>;
  }

  if (!course) {
    return <div style={{ textAlign: 'center', padding: '100px', fontSize: '20px' }}>Курс не найден</div>;
  }

  return (
    <div className="material-page">
      <Header isAuth={isAuth} onLoginClick={() => setIsAuthModalOpen(true)} />
      
      <main className="material-content">
        <div className="material-top-nav">
          <Link to="/" className="back-link">← На главную</Link>
          <div className="breadcrumbs">
            {course.topics?.[0]?.title || 'Курсы'} / {course.title}
          </div>
        </div>

        <div className="material-layout">
          <aside className="material-sidebar">
            <button 
              className={`btn-mark-completed-top ${isCompleted ? 'completed' : ''}`}
              onClick={handleCompleteClick}
            >
              {isCompleted ? (
                <><span className="check-icon">✓</span> Пройдено</>
              ) : (
                <><span className="checkbox-icon"></span> Отметить пройденным</>
              )}
            </button>

            <div className="promo-card">
              <span className="promo-label">ПЕРСОНАЛЬНЫЙ ПОДБОР</span>
              <h3>Подберём материалы под ваши задачи</h3>
              <p>Ответьте на 3 коротких вопроса о вашем бизнесе — соберём персональную подборку или пошаговую траекторию.</p>
              <button className="btn-primary w-100" onClick={handleGoToOnboarding}>
                Пройти опрос →
              </button>
              <span className="promo-hint">Изменить параметры можно в профиле</span>
            </div>
          </aside>

          <main className="material-main">
            <div className="material-header">
              <div>
                <div className="course-meta-tags">
                  {course.duration_minutes && <span>{course.duration_minutes} мин</span>}
                  <span>{course.kind === 'course' ? 'Курс' : course.kind === 'article' ? 'Статья' : 'Документ'}</span>
                  <span>{course.access_type === 'free' ? 'Бесплатно' : 'Платно'}</span>
                </div>
                <h1 className="course-title">{course.title}</h1>
              </div>
              
              <div className="material-header-right">
                <button 
                  className={`bookmark-btn-material ${isFavorite ? 'active' : ''}`} 
                  onClick={handleFavoriteClick}
                >
                  <svg width="24" height="24" viewBox="0 0 24 24" fill={isFavorite ? "#f59e0b" : "none"} xmlns="http://www.w3.org/2000/svg">
                    <path d="M17 3H7C5.9 3 5 3.9 5 5V21L12 18L19 21V5C19 3.9 18.1 3 17 3Z" stroke={isFavorite ? "#f59e0b" : "#1a1a1a"} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
                {course.offers?.[0]?.price?.amount_minor && (
                  <div className="header-price">
                    {course.offers[0].price.amount_minor / 100} ₽
                  </div>
                )}
              </div>
            </div>

            <p className="course-subtitle">{course.description || 'Описание материала'}</p>

            {/* БЛОК С ОБЪЯСНЕНИЕМ ОТ ИИ (если авторизован) */}
            {aiExplanation && (
              <div className="card-ai-block" style={{ marginBottom: '24px', padding: '16px', background: '#f8fbff', borderRadius: '12px', borderLeft: '4px solid #3b82f6' }}>
                <strong>Почему вам подойдёт:</strong> {aiExplanation}
              </div>
            )}

            <button className="btn-buy-mobile" onClick={handleBuyClick}>Купить курс →</button>

            <div className="material-columns">
              <section className="learn-section">
                <h2>Чему вы научитесь</h2>
                <div className="learn-grid">
                  {course.skills?.length > 0 ? (
                    course.skills.map((skill: any, index: number) => (
                      <div key={skill.id} className="learn-item">
                        <span className="learn-number">0{index + 1}</span>
                        <div>
                          <h4>{skill.title}</h4>
                          <p>Навык, который вы освоите в этом материале.</p>
                        </div>
                      </div>
                    ))
                  ) : (
                    <p>Информация об навыках отсутствует</p>
                  )}
                </div>
              </section>

              <section className="program-section">
                <h2>Программа курса</h2>
                <p className="program-subtitle">{course.topics?.length || 0} темы</p>
                <div className="program-list">
                  {course.topics?.length > 0 ? (
                    course.topics.map((topic: any, index: number) => (
                      <div key={topic.id} className="program-item">
                        <div className="program-header">
                          <span className="prog-num">0{index + 1}</span>
                          <div>
                            <h4>{topic.title}</h4>
                            <span className="prog-count">Модуль</span>
                          </div>
                          <span className="prog-plus">+</span>
                        </div>
                      </div>
                    ))
                  ) : (
                    <p>Программа курса в разработке</p>
                  )}
                </div>
              </section>
            </div>

            <div className="materials-notice">
              Материалы курса появятся в вашем профиле после покупки.
            </div>

            {relatedMaterials.length > 0 && (
              <div className="recommended-section">
                <h2>Продолжите обучение</h2>
                <p>Другие курсы, которые помогут развивать ваш бизнес.</p>
                <div className="materials-grid">
                  {relatedMaterials.map((m) => (
                    <MaterialCard 
                      key={m.id} 
                      {...m} 
                      isAuth={isAuth} 
                      isOnboardingDone={true} 
                      lockedText="Рекомендация: связанный материал" 
                    />
                  ))}
                </div>
              </div>
            )}
          </main>
        </div>
      </main>

      <Footer />
      <SuccessModal isOpen={isSuccessOpen} onClose={() => setIsSuccessOpen(false)} />
      <AuthModal isOpen={isAuthModalOpen} onClose={() => setIsAuthModalOpen(false)} />
      {showToast && (
        <div className="toast-notification">
          <span className="toast-icon">✓</span> Материал добавлен в избранное
        </div>
      )}
    </div>
  );
};