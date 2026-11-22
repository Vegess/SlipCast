import { Injectable, signal } from '@angular/core';

export type Theme = 'dusk' | 'light' | 'neon';
const KEY = 'slipcast_theme';

/**
 * Colours used inside charts (ECharts draws on canvas, so it can't read CSS variables).
 * Keep in sync with the palettes in tailwind.config.js. Charts are written with the Dusk
 * values; ChartComponent swaps them for the Light or Neon equivalents when those themes are on.
 */
export const DUSK = {
  canvas: '#172033', panel: '#1F2A40', raised: '#28354F', line: '#34425E', grid: '#2A3650', dim: '#46546F',
  fg: '#EEF2F8', muted: '#A3AEC4', accent: '#F5B83D', info: '#6EA8FE', ok: '#4FD1A5', bad: '#FF7A7A',
  violet: '#A78BFA', sky: '#5DB0E8',
} as const;
export const LIGHT: Record<keyof typeof DUSK, string> = {
  canvas: '#F3F5FA', panel: '#FFFFFF', raised: '#EAEEF5', line: '#D3DAE6', grid: '#E4E9F1', dim: '#C9D1DE',
  fg: '#18202F', muted: '#566279', accent: '#C27C0E', info: '#2459D6', ok: '#0E9470', bad: '#D2403F',
  violet: '#6D3FD9', sky: '#1F8BC4',
};
export const NEON: Record<keyof typeof DUSK, string> = {
  canvas: '#090D12', panel: '#0F151D', raised: '#16202B', line: '#223142', grid: '#18232F', dim: '#2E4054',
  fg: '#E7FBF8', muted: '#94A9B6', accent: '#2EE6C5', info: '#5CC8FF', ok: '#4BE38A', bad: '#FF6B8E',
  violet: '#B78CFF', sky: '#5CC8FF',
};
export const PALETTES: Record<Theme, Record<keyof typeof DUSK, string>> = { dusk: DUSK, light: LIGHT, neon: NEON };
const swap = (to: Record<keyof typeof DUSK, string>) =>
  new Map(Object.entries(DUSK).map(([k, v]) => [v.toUpperCase(), to[k as keyof typeof DUSK]]));
const SWAPS: Record<Theme, Map<string, string> | null> = { dusk: null, light: swap(LIGHT), neon: swap(NEON) };

/** Replaces Dusk colours anywhere in an ECharts option object (strings only, recursively). */
export function forTheme<T>(value: T, theme: Theme): T {
  const map = SWAPS[theme];
  if (!map) return value;
  const walk = (v: unknown): unknown => {
    if (typeof v === 'string') return map.get(v.toUpperCase()) ?? v;
    if (Array.isArray(v)) return v.map(walk);
    if (v && typeof v === 'object' && Object.getPrototypeOf(v) === Object.prototype) {
      return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, walk(x)]));
    }
    return v;
  };
  return walk(value) as T;
}
export function toLight<T>(value: T): T { return forTheme(value, 'light'); }

export function readTheme(): Theme {
  try {
    const t = localStorage.getItem(KEY);
    return t === 'light' || t === 'neon' ? t : 'dusk';
  } catch { return 'dusk'; }
}

@Injectable({ providedIn: 'root' })
export class ThemeService {
  readonly theme = signal<Theme>(readTheme());

  constructor() { this.apply(this.theme()); }

  set(theme: Theme) {
    this.theme.set(theme);
    try { localStorage.setItem(KEY, theme); } catch { /* storage blocked */ }
    this.apply(theme);
  }

  private apply(theme: Theme) {
    document.documentElement.dataset['theme'] = theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', PALETTES[theme].canvas);
  }
}
