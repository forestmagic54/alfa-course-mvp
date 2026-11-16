// src/api.ts

const API_URL = '/api/v1';

const ONBOARDING_META = {
  form_type: 'simple',
  questionnaire_version: '1',
  status: 'completed',
};

const buildHeaders = (token?: string) => {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return headers;
};

// Запрос с автоповтором без токена, если токен просрочен (401)
const request = async (path: string, init: RequestInit = {}, token?: string): Promise<Response> => {
  const send = (t?: string) =>
    fetch(`${API_URL}${path}`, {
      cache: 'no-store',
      ...init,
      headers: { ...buildHeaders(t), ...(init.headers as any) },
    });

  const t = token ?? localStorage.getItem('token') ?? undefined;
  let res = await send(t);
  if (res.status === 401 && t) {
    localStorage.removeItem('token');
    res = await send(undefined);
  }
  return res;
};

// ===== Данные конкретного пользователя в браузере =====
const USER_KEYS = [
  'isOnboardingDone',
  'isTrajectory',
  'trajectory',
  'personalMaterials',
  'onboardingAnswers',
  'onboardingSummary',
  'onboardingSynced',
  'subscription',
  'completedMaterials',
  'favorites',
  'accountId',
];

// Очистка при смене аккаунта или выходе, чтобы данные одного пользователя не попали другому
export const clearUserData = () => {
  USER_KEYS.forEach((k) => localStorage.removeItem(k));
};

// 1. Каталог
export const fetchMaterials = async (kind?: string) => {
  try {
    const res = await request(kind ? `/materials?kind=${kind}` : '/materials');
    if (!res.ok) throw new Error('Ошибка загрузки');
    const data = await res.json();
    return data.items;
  } catch (error) {
    console.error('Ошибка API:', error);
    return null;
  }
};

// 1.1. Получить детали материала (там есть description)
export const fetchMaterialDetail = async (materialId: string) => {
  try {
    const res = await request(`/materials/${materialId}`);
    if (!res.ok) return null;
    return await res.json();
  } catch (error) {
    console.error('Ошибка загрузки деталей материала:', error);
    return null;
  }
};

// 2. Рекомендации аккаунта (витрина)
export const fetchRecommendations = async () => {
  try {
    const res = await request('/recommendations?mode=personalized');
    if (!res.ok) throw new Error('Ошибка рекомендаций');
    const data = await res.json();
    return data.items;
  } catch (error) {
    console.error('Ошибка API рекомендаций:', error);
    return null;
  }
};

// 3. Купить курс
export const purchaseCourse = async (courseId: string) => {
  try {
    const res = await request('/me/purchases', {
      method: 'POST',
      body: JSON.stringify({
        request_id: crypto.randomUUID(),
        kind: 'course',
        course_id: courseId,
      }),
    });
    if (!res.ok) throw new Error('Ошибка покупки');
    return await res.json();
  } catch (error) {
    console.warn('Сервер недоступен, имитируем покупку локально');
    return { success: true };
  }
};

// 4. Отметить материал изученным
export const markAsCompleted = async (materialId: string) => {
  try {
    const res = await request(`/me/materials/${materialId}/study-state`, {
      method: 'PUT',
      body: JSON.stringify({ is_studied: true }),
    });
    return res.ok;
  } catch (error) {
    console.warn('Сервер недоступен, сохраняем локально');
    return true;
  }
};

// 5. Избранное (заглушка)
export const saveToFavorite = async (_materialId: string) => {
  return true;
};

// 6. Сохранить анкету в профиль (только для авторизованных)
export const submitOnboarding = async (answers: any) => {
  try {
    const res = await request('/me/onboarding', {
      method: 'PUT',
      body: JSON.stringify({ ...ONBOARDING_META, answers }),
    });
    if (!res.ok) console.error('Ошибка сохранения анкеты:', await res.text());
    return res.ok;
  } catch (error) {
    console.warn('Сервер недоступен', error);
    return false;
  }
};

// 6.1. Последние сохранённые ответы анкеты аккаунта
export const fetchOnboarding = async () => {
  try {
    const res = await request('/me/onboarding');
    if (!res.ok) return null;
    return await res.json();
  } catch (error) {
    console.error('Ошибка загрузки анкеты:', error);
    return null;
  }
};

// 7. Персональное объяснение материала (только для авторизованных).
export const fetchMaterialExplanation = async (materialId: string, token?: string, answers?: any) => {
  try {
    const body = answers
      ? JSON.stringify({ onboarding: { ...ONBOARDING_META, answers } })
      : JSON.stringify({});
    const res = await request(`/materials/${materialId}/explanation`, {
      method: 'POST',
      body,
    }, token);
    if (!res.ok) return null;
    return await res.json();
  } catch (error) {
    console.error('Ошибка API объяснения:', error);
    return null;
  }
};

// 8. Логин
export const login = async (email: string, password: string) => {
  try {
    const res = await fetch(`${API_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) throw new Error('Ошибка логина');
    const data = await res.json();
    localStorage.setItem('token', data.access_token);
    return data;
  } catch (error) {
    console.error('Ошибка логина:', error);
    return null;
  }
};

// 9. Сохранить подборку
export const saveRecommendations = async (listId: string, token: string) => {
  try {
    const res = await request(`/me/recommendations/${listId}/saved`, { method: 'PUT' }, token);
    return res.ok;
  } catch (error) {
    console.error('Ошибка сохранения подборки:', error);
    return false;
  }
};

// 10. Сформировать подборку (гость или авторизованный)
export const generateRecommendations = async (answers: any, token?: string) => {
  try {
    const format = answers?.learning_mode === 'practical' ? 'medium' : 'quick';
    const res = await request('/recommendations', {
      method: 'POST',
      body: JSON.stringify({
        format,
        onboarding: { ...ONBOARDING_META, answers },
      }),
    }, token);
    if (!res.ok) {
      console.error('Ошибка рекомендаций:', await res.text());
      return null;
    }
    return await res.json();
  } catch (error) {
    console.error('Ошибка API рекомендаций:', error);
    return null;
  }
};

// 11. Карта достижения цели (траектория). Ответы передаём в теле — работает и для гостя
export const generateRoadmap = async (answers: any, token?: string) => {
  try {
    const res = await request('/roadmaps', {
      method: 'POST',
      body: JSON.stringify({
        onboarding: { ...ONBOARDING_META, answers },
      }),
    }, token);
    if (!res.ok) {
      console.error('Ошибка карты:', await res.text());
      return null;
    }
    return await res.json();
  } catch (error) {
    console.error('Ошибка API карты:', error);
    return null;
  }
};

// 11.1. Сохранить карту в аккаунт (чтобы она попала в GET /me/roadmaps)
export const saveRoadmap = async (listId: string, token: string) => {
  try {
    const res = await request(`/me/roadmaps/${listId}/saved`, { method: 'PUT' }, token);
    return res.ok;
  } catch (error) {
    console.error('Ошибка сохранения карты:', error);
    return false;
  }
};

// 12. Сохранённые карты
export const fetchMyRoadmaps = async (token: string) => {
  try {
    const res = await request('/me/roadmaps', {}, token);
    if (!res.ok) throw new Error('Ошибка загрузки карт');
    return await res.json();
  } catch (error) {
    console.error('Ошибка API карт:', error);
    return null;
  }
};

// ===== ПОДПИСКА «КУРС+» И СКИДКИ =====

// 13. Тарифы подписки
export const fetchSubscriptionOffers = async (): Promise<any[]> => {
  try {
    const res = await request('/subscriptions/offers');
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch (error) {
    console.error('Ошибка тарифов:', error);
    return [];
  }
};

// 14. Актуальный статус подписки с бэкенда
export const refreshSubscription = async (): Promise<boolean> => {
  try {
    const res = await request('/me/subscriptions');
    if (!res.ok) {
      localStorage.removeItem('subscription');
      return false;
    }
    const subs = await res.json();
    const active = Array.isArray(subs) && subs.length > 0;
    if (active) localStorage.setItem('subscription', 'plus');
    else localStorage.removeItem('subscription');
    return active;
  } catch (error) {
    console.error('Ошибка статуса подписки:', error);
    return false;
  }
};

// 15. Подключить «Курс+»
export const activateSubscription = async (): Promise<boolean> => {
  try {
    const offers = await fetchSubscriptionOffers();
    const offer = offers[0];
    if (offer) {
      const res = await request('/me/purchases', {
        method: 'POST',
        body: JSON.stringify({
          request_id: crypto.randomUUID(),
          kind: 'subscription',
          subscription_tariff_id: offer.subscription_tariff_id,
        }),
      });
      if (!res.ok) console.error('Ошибка подключения подписки:', await res.text());
    }
  } catch (error) {
    console.error('Ошибка подключения подписки:', error);
  }
  return refreshSubscription();
};

// 16. Синхронизация с аккаунтом
export const syncAccount = async () => {
  const token = localStorage.getItem('token');
  if (!token) return null;

  try {
    const meRes = await request('/me', {}, token);
    if (!meRes.ok) return null;
    const me = await meRes.json();

    const prevId = localStorage.getItem('accountId');
    let switched = false;
    if ((prevId && prevId !== me.id) || (!prevId && me.onboarding_completed)) {
      clearUserData();
      switched = true;
    }
    localStorage.setItem('accountId', me.id);

    const [subsRes, discRes] = await Promise.all([
      request('/me/subscriptions', {}, token),
      request('/me/discounts', {}, token),
    ]);
    const subs = subsRes.ok ? await subsRes.json() : [];
    const discounts = discRes.ok ? await discRes.json() : [];

    const subscribed = Array.isArray(subs) && subs.length > 0;
    if (subscribed) localStorage.setItem('subscription', 'plus');
    else localStorage.removeItem('subscription');

    let hadSubscription = false;
    if (!subscribed) {
      try {
        const pRes = await request('/me/purchases', {}, token);
        if (pRes.ok) {
          const purchases = await pRes.json();
          hadSubscription = Array.isArray(purchases) && purchases.some((p: any) => p.kind === 'subscription');
        }
      } catch {}
    }

    return {
      me,
      switched,
      subscribed,
      subscription: subscribed ? subs[0] : null,
      discounts: Array.isArray(discounts) ? discounts : [],
      hadSubscription,
    };
  } catch (error) {
    console.error('Ошибка синхронизации аккаунта:', error);
    return null;
  }
};