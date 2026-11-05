import { Injectable, signal } from '@angular/core';

export type Theme = 'dusk' | 'light';
const KEY = 'slipcast_theme';

/**
 * Colours used inside charts (ECharts draws on canvas, so it can't read CSS variables).
 * Keep in sync with the palettes in tailwind.config.js. Charts are written with the Dusk
 * values; ChartComponent swaps them for the light equivalents when the light theme is on.
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
const TO_LIGHT = new Map(Object.entries(DUSK).map(([k, v]) => [v.toUpperCase(), LIGHT[k as keyof typeof DUSK]]));

/** Replaces Dusk colours anywhere in an ECharts option object (strings only, recursively). */
export function toLight<T>(value: T): T {
  if (typeof value === 'string') return (TO_LIGHT.get(value.toUpperCase()) ?? value) as T;
  if (Array.isArray(value)) return value.map(toLight) as T;
  if (value && typeof value === 'object' && Object.getPrototypeOf(value) === Object.prototype) {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, toLight(v)])) as T;
  }
  return value;
}

export function readTheme(): Theme {
  try { return localStorage.getItem(KEY) === 'light' ? 'light' : 'dusk'; } catch { return 'dusk'; }
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
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'light' ? LIGHT.canvas : DUSK.canvas);
  }
}
