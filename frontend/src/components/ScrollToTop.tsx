// src/components/ScrollToTop.tsx
import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

export const ScrollToTop = () => {
  const { pathname } = useLocation();

  useEffect(() => {
    // При смене страницы (pathname) скроллим в самый верх
    window.scrollTo(0, 0);
  }, [pathname]);

  return null; // Этот компонент ничего не рисует, он просто работает
};