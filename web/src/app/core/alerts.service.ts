import { Injectable, computed, effect, inject, signal, untracked } from '@angular/core';
import { Api } from './api.service';
import { AuthService } from './auth.service';

export interface Alert {
  id: string; project_id: string; project_name: string; kind: string;
  severity: 'info' | 'warning' | 'critical'; message: string; data: Record<string, unknown>; created_at: string;
}

const SEEN_KEY = 'slipcast_alerts_seen';
const POLL_MS = 60_000;

/** The bell's alerts for the current workspace, plus short-lived toasts for ones that arrive live. */
@Injectable({ providedIn: 'root' })
export class AlertsService {
  private api = inject(Api);
  private auth = inject(AuthService);
  readonly items = signal<Alert[]>([]);
  readonly toasts = signal<Alert[]>([]);
  /** Bumped when a new alert arrives, so the bell can ring. */
  readonly rings = signal(0);
  private readonly seenAt = signal(this.readSeen());
  readonly unseen = computed(() => this.items().filter((a) => a.created_at > this.seenAt()).length);
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor() {
    effect(() => {
      const ws = this.auth.workspace()?.id;
      untracked(() => {
        if (this.timer) clearInterval(this.timer);
        this.items.set([]);
        if (!ws) return;
        this.load();
        this.timer = setInterval(() => this.load(), POLL_MS);
      });
    });
  }

  async load() {
    const ws = this.auth.workspace()?.id;
    if (!ws) return;
    try {
      const fresh = await this.api.get<Alert[]>(`/workspaces/${ws}/alerts`);
      const known = new Set(this.items().map((a) => a.id));
      if (this.items().length && fresh.some((a) => !known.has(a.id))) this.rings.update((n) => n + 1);
      this.items.set(fresh);
    } catch { /* the bell just stays as it was */ }
  }

  /** An alert that arrived on a live stream: show it now, keep it in the bell. */
  push(alert: Alert) {
    if (this.items().some((a) => a.id === alert.id)) return;
    this.items.update((xs) => [alert, ...xs].slice(0, 30));
    this.toasts.update((ts) => [...ts, alert].slice(-3));
    this.rings.update((n) => n + 1);
    setTimeout(() => this.dismiss(alert.id), 7000);
  }

  dismiss(id: string) { this.toasts.update((ts) => ts.filter((t) => t.id !== id)); }

  markSeen() {
    const newest = this.items()[0]?.created_at;
    if (!newest) return;
    this.seenAt.set(newest);
    try { localStorage.setItem(SEEN_KEY, newest); } catch { /* storage blocked */ }
  }

  private readSeen(): string {
    try { return localStorage.getItem(SEEN_KEY) ?? ''; } catch { return ''; }
  }
}
