/** 極簡 hash router。GitHub Pages 沒有 SPA fallback，BrowserRouter 重整必 404。 */
import { useEffect, useState } from 'react';

export function parseHash(h = window.location.hash) {
  const path = h.replace(/^#\/?/, '');
  const [kind, ...rest] = path.split('/');
  const arg = decodeURIComponent(rest.join('/'));
  if (kind === 'i') return { view: 'ingredient', key: arg };
  if (kind === 's') return { view: 'section', key: arg };
  if (kind === 'p') return { view: 'procedure', key: arg };
  if (kind === 'a') return { view: 'appendix', key: arg };
  if (kind === 'about') return { view: 'about' };
  if (kind === 'changes') return { view: 'changes' };
  return { view: 'home', q: kind ? decodeURIComponent(kind) : '' };
}

export function useHashRoute() {
  const [route, setRoute] = useState(() => parseHash());
  useEffect(() => {
    const on = () => setRoute(parseHash());
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);
  return route;
}

export const go = (hash) => {
  window.location.hash = hash;
};
