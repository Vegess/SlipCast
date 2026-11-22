import { Component, OnDestroy, computed, effect, inject, signal, untracked } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { Alert, AlertsService } from '../../core/alerts.service';
import { Api, errorMessage } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { API_URL } from '../../core/config';
import { ThemeService } from '../../core/theme.service';

type Level = 'high' | 'medium' | 'low' | null;
interface Promise_ {
  project_id: string; project: string; color: string; template: string; module: string; id: string; title: string;
  owner: string; due: string | null; when: string | null; stage: string | null; risk: number | null; level: Level; reasons: string[];
}
interface Module { template: string; module: string; projects: number; due_soon: number; high_risk: number; scored: number; hit_rate: number | null }
interface Card {
  id: string; name: string; color: string; template: string; module: string; noun: string; open: number; due_soon: number;
  high_risk: number; forecast_p85: string | null; hit_rate: number | null; scored: number;
}
interface Activity { at: string; project_id: string; project: string; task_id: string | null; title: string; stage: string }
interface Room {
  available: boolean; reason: string; now: string; days: string[];
  counts: { due_soon: number; high_risk: number; overdue: number };
  modules: Module[]; projects: Card[]; promises: Promise_[]; activity: Activity[];
}

const NOUNS: Record<string, string> = { software: 'tickets', shipments: 'orders', services: 'jobs' };
const STROKE: Record<string, string> = { software: 'stroke-info', shipments: 'stroke-accent', services: 'stroke-violet' };
const TEXT: Record<string, string> = { software: 'text-info', shipments: 'text-accent', services: 'text-violet' };

@Component({
  selector: 'app-control-room',
  imports: [RouterLink],
  template: `
  <div class="mx-auto max-w-[1500px] px-4 py-6 sm:px-8">
    <header class="anim-fade flex flex-wrap items-end gap-4">
      <div class="mr-auto">
        <h1 class="flex items-center gap-3 font-display text-3xl font-bold sm:text-4xl">Control Room
          <span class="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-normal"
                [class]="live() === 'live' ? 'bg-ok/10 text-ok-strong' : 'bg-raised text-muted'">
            <span class="live-dot" [class]="live() === 'live' ? 'bg-ok' : 'bg-muted'" aria-hidden="true"></span>{{ live() === 'live' ? 'Live' : 'Connecting…' }}
          </span></h1>
        <p class="note mt-1">Every promise due in the next 7 days, across all your projects, riskiest first. Risks come from each project's own model.</p>
      </div>
      <p class="font-display text-2xl tabular-nums text-muted" aria-label="Current time">{{ clock() }}</p>
      @if (theme.theme() !== 'neon') { <button class="btn" (click)="theme.set('neon')">Switch to Neon</button> }
    </header>

    @if (error()) { <p class="mt-4 text-sm text-bad">{{ error() }}</p> }
    @if (room(); as r) {
      @if (!r.available) {
        <div class="card mt-6 text-sm text-muted">{{ r.reason }} <a routerLink="/projects" class="text-accent hover:underline">Go to projects</a></div>
      } @else {
        <!-- Modules: promises due soon, high risk, and the ledger's hit rate as a ring -->
        <section class="mt-6 grid gap-3 md:grid-cols-3" aria-label="Modules">
          @for (m of r.modules; track m.template; let i = $index) {
            <div class="card anim-rise flex items-center gap-4 p-4" [style.--i]="i">
              <svg width="76" height="76" viewBox="0 0 76 76" class="shrink-0" role="img"
                   [attr.aria-label]="m.hit_rate == null ? 'No scored forecasts yet' : pct(m.hit_rate) + ' of scored forecasts were right'">
                <circle cx="38" cy="38" r="31" class="stroke-line" stroke-width="7" fill="none"/>
                <circle cx="38" cy="38" r="31" fill="none" stroke-width="7" stroke-linecap="round" transform="rotate(-90 38 38)"
                        [attr.class]="'ring-fill ' + stroke(m.template)" [style.--len]="ring" [attr.stroke-dasharray]="ring"
                        [attr.stroke-dashoffset]="ring * (1 - (m.hit_rate ?? 0))" [style.animation-delay]="i * 150 + 'ms'"/>
                <text x="38" y="43" text-anchor="middle" class="fill-fg font-display text-[17px] font-semibold">{{ m.hit_rate == null ? '–' : pct(m.hit_rate) }}</text>
              </svg>
              <div class="min-w-0">
                <p class="font-display text-lg font-semibold" [class]="text(m.template)">{{ m.module }}</p>
                <p class="text-sm"><b class="font-semibold">{{ m.due_soon }}</b> {{ noun(m.template) }} due · <b class="font-semibold" [class.text-bad]="m.high_risk">{{ m.high_risk }}</b> at high risk</p>
                <p class="text-xs text-muted">Track record: {{ m.scored ? m.scored + ' forecasts scored' : 'nothing scored yet' }}</p>
              </div>
            </div>
          }
        </section>

        <!-- The week: every promise is a dot on its due day; high-risk ones pulse -->
        <section class="card mt-4" aria-labelledby="week-title">
          <div class="flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <h2 id="week-title" class="section-title">The next 7 days</h2>
            <p class="note mr-auto">Each dot is one promise on its due day. {{ r.counts.overdue }} already overdue.</p>
            <p class="flex gap-3 text-xs text-muted" aria-hidden="true">
              <span class="flex items-center gap-1.5"><span class="h-2.5 w-2.5 rounded-full bg-bad"></span>High risk</span>
              <span class="flex items-center gap-1.5"><span class="h-2.5 w-2.5 rounded-full bg-accent"></span>Medium</span>
              <span class="flex items-center gap-1.5"><span class="h-2.5 w-2.5 rounded-full bg-ok/80"></span>Low</span>
              <span class="flex items-center gap-1.5"><span class="h-2.5 w-2.5 rounded-full bg-muted/60"></span>No score</span>
            </p>
          </div>
          <svg [attr.viewBox]="'0 0 ' + W + ' ' + H" class="mt-3 w-full" role="img" aria-label="Promises by due day, coloured by risk">
            @for (d of columns(); track d.key; let i = $index) {
              <g [attr.transform]="'translate(' + (i * colW) + ',0)'">
                <rect x="4" y="0" [attr.width]="colW - 8" [attr.height]="H - 30" rx="10" [attr.class]="d.key === 'overdue' ? 'fill-bad/5' : i === 1 ? 'fill-accent/5' : 'fill-raised/40'"/>
                @for (p of d.items; track p.id; let j = $index) {
                  <g class="cursor-pointer" (click)="open(p)">
                    <title>{{ p.title }} · {{ p.project }}{{ p.risk != null ? ' · ' + pct(p.risk) + ' risk' : '' }}</title>
                    @if (p.level === 'high') { <circle [attr.cx]="dotX(j)" [attr.cy]="dotY(j)" r="5" class="ring-pulse fill-none stroke-bad" stroke-width="1.5" [style.animation-delay]="(j % 7) * 0.3 + 's'"/> }
                    <circle [attr.cx]="dotX(j)" [attr.cy]="dotY(j)" r="5" class="dot-in" [style.animation-delay]="(i * 60 + j * 12) + 'ms'"
                            [attr.class]="'dot-in ' + (p.level === 'high' ? 'fill-bad' : p.level === 'medium' ? 'fill-accent' : p.level === 'low' ? 'fill-ok/80' : 'fill-muted/60')"/>
                  </g>
                }
                @if (d.more) { <text [attr.x]="colW / 2" [attr.y]="H - 40" text-anchor="middle" class="fill-muted text-[11px]">+{{ d.more }} more</text> }
                <text [attr.x]="colW / 2" [attr.y]="H - 12" text-anchor="middle" class="text-[12px]" [attr.class]="d.key === 'overdue' ? 'fill-bad text-[12px]' : 'fill-muted text-[12px]'">{{ d.label }}</text>
              </g>
            }
          </svg>
        </section>

        <div class="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
          <!-- At risk first -->
          <section class="card" aria-labelledby="list-title">
            <div class="flex flex-wrap items-center gap-2">
              <h2 id="list-title" class="section-title mr-auto">At risk first</h2>
              @for (f of filters(); track f[0]) {
                <button class="rounded-full px-3 py-1 text-xs ring-1 transition-colors" (click)="filter.set(f[0])"
                        [class]="filter() === f[0] ? 'bg-accent/15 text-fg ring-accent/60' : 'text-muted ring-line hover:text-fg'">{{ f[1] }}</button>
              }
            </div>
            <ul class="mt-3 divide-y divide-line/70 text-sm">
              @for (p of shown(); track p.id; let i = $index) {
                <li class="anim-rise flex items-start gap-3 py-2.5" [style.--i]="i < 12 ? i : 12" [class.live-flash]="flashed().has(p.id)">
                  <span class="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full" [style.background]="p.color" aria-hidden="true"></span>
                  <div class="min-w-0 flex-1">
                    <a [routerLink]="['/projects', p.project_id, 'board']" class="block truncate font-medium hover:underline">{{ p.title }}</a>
                    <p class="text-xs text-muted"><span [class]="text(p.template)">{{ p.module }}</span> · {{ p.project }} · {{ p.owner || 'Unassigned' }} · {{ dueText(p) }}{{ p.stage ? ' · ' + label(p.stage) : '' }}</p>
                    @if (p.reasons.length) { <p class="mt-0.5 text-xs text-muted">{{ p.reasons.join(' · ') }}</p> }
                  </div>
                  @if (p.risk != null) {
                    <span class="pill shrink-0" [class]="p.level === 'high' ? 'bg-bad/15 text-bad' : p.level === 'medium' ? 'bg-accent/15 text-accent' : 'bg-ok/10 text-ok-strong'">{{ pct(p.risk) }}</span>
                  } @else { <span class="shrink-0 text-xs text-muted">no score</span> }
                </li>
              } @empty { <li class="py-3 text-muted">Nothing due in the next 7 days{{ filter() !== 'all' ? ' for this module' : '' }}.</li> }
            </ul>
            @if (r.promises.length > shown().length && filter() === 'all') { <p class="mt-2 text-xs text-muted">Showing the riskiest {{ shown().length }} of {{ r.promises.length }}.</p> }
          </section>

          <!-- Live feed -->
          <section class="card self-start" aria-labelledby="feed-title" aria-live="polite">
            <h2 id="feed-title" class="section-title">Live feed</h2>
            <p class="note mt-1">The latest stage changes in every project. New ones slide in as they happen.</p>
            <ol class="mt-3 space-y-2.5 text-sm">
              @for (a of r.activity.slice(0, 14); track a.at + a.title + a.stage) {
                <li class="flex gap-3" [class.feed-new]="fresh().has(a.at + a.title + a.stage)">
                  <span class="mt-1 flex flex-col items-center" aria-hidden="true"><span class="h-2 w-2 rounded-full" [class]="stageDot(a.stage)"></span></span>
                  <div class="min-w-0 flex-1">
                    <p class="truncate"><span class="text-muted">{{ a.project }} ·</span> {{ a.title }}</p>
                    <p class="text-xs text-muted">{{ label(a.stage) }} · {{ ago(a.at) }}</p>
                  </div>
                </li>
              } @empty { <li class="text-muted">No activity yet.</li> }
            </ol>
          </section>
        </div>

        <!-- Projects -->
        <section class="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-label="Projects">
          @for (c of r.projects; track c.id; let i = $index) {
            <a [routerLink]="['/projects', c.id, 'delivery']" class="card lift anim-rise block p-4" [style.--i]="i">
              <p class="flex items-center gap-2 font-medium"><span class="h-2.5 w-2.5 rounded-full" [style.background]="c.color"></span><span class="truncate">{{ c.name }}</span>
                <span class="ml-auto text-xs" [class]="text(c.template)">{{ c.module }}</span></p>
              <p class="mt-2 text-sm">{{ c.open }} open · {{ c.due_soon }} due this week · <span [class.text-bad]="c.high_risk">{{ c.high_risk }} high risk</span></p>
              <p class="mt-1 text-xs text-muted">All open {{ c.noun }}s done by {{ c.forecast_p85 ?? '–' }} (85% likely) · Track record {{ c.hit_rate == null ? 'not scored yet' : pct(c.hit_rate) + ' of ' + c.scored }}</p>
            </a>
          }
        </section>
      }
    } @else if (!error()) {
      <div class="mt-6 grid gap-3 md:grid-cols-3">@for (i of [0, 1, 2]; track i) { <div class="skeleton h-28"></div> }</div>
      <div class="skeleton mt-4 h-48"></div>
    }
  </div>`,
  styles: [`
    .ring-fill { animation: ring-fill 1.4s cubic-bezier(.2,.8,.2,1) backwards; }
    @keyframes ring-fill { from { stroke-dashoffset: var(--len); } }
    .dot-in { transform-box: fill-box; transform-origin: center; animation: dot-in .5s cubic-bezier(.3,1.6,.5,1) backwards; }
    @keyframes dot-in { from { transform: scale(0); opacity: 0; } }
    .feed-new { animation: feed-in .7s cubic-bezier(.2,.8,.2,1), sc-flash 2.2s ease-out; }
    @keyframes feed-in { from { opacity: 0; transform: translateX(16px); } }
    @media (prefers-reduced-motion: reduce) { .ring-fill, .dot-in, .feed-new { animation: none; } }
  `],
})
export class ControlRoomPage implements OnDestroy {
  private api = inject(Api);
  private auth = inject(AuthService);
  private alerts = inject(AlertsService);
  private router = inject(Router);
  readonly theme = inject(ThemeService);

  readonly room = signal<Room | null>(null);
  readonly error = signal('');
  readonly live = signal<'off' | 'connecting' | 'live'>('off');
  readonly filter = signal('all');
  readonly flashed = signal<ReadonlySet<string>>(new Set());
  readonly fresh = signal<ReadonlySet<string>>(new Set());
  readonly clock = signal(this.time());

  readonly ring = 2 * Math.PI * 31;
  readonly W = 960; readonly H = 200; readonly colW = 960 / 9;
  private readonly perCol = 24;

  private source: EventSource | null = null;
  private retries = 0;
  private timers: ReturnType<typeof setTimeout>[] = [];
  private refreshTimer: ReturnType<typeof setTimeout> | null = null;
  private pendingIds = new Set<string>();
  private ticker = setInterval(() => this.clock.set(this.time()), 1000);
  private ws = '';

  constructor() {
    effect(() => {
      const ws = this.auth.workspace()?.id;
      untracked(() => {
        if (!ws || ws === this.ws) return;
        this.ws = ws;
        this.load();
        this.connect();
      });
    });
  }

  readonly filters = computed(() => [['all', 'All'], ...(this.room()?.modules ?? []).map((m) => [m.template, m.module])]);
  readonly shown = computed(() => {
    const f = this.filter(), ps = this.room()?.promises ?? [];
    return (f === 'all' ? ps : ps.filter((p) => p.template === f)).slice(0, 25);
  });

  /** Overdue, then today and the next 7 days. */
  readonly columns = computed(() => {
    const r = this.room();
    if (!r?.available) return [];
    const by = new Map<string, Promise_[]>();
    for (const p of r.promises) {
      const key = !p.due ? 'none' : p.due < r.days[0] ? 'overdue' : p.due;
      by.set(key, [...(by.get(key) ?? []), p]);
    }
    const col = (key: string, label: string) => {
      const items = by.get(key) ?? [];
      return { key, label, items: items.slice(0, this.perCol), more: Math.max(0, items.length - this.perCol) };
    };
    return [col('overdue', 'Overdue'), ...r.days.map((d, i) => col(d, i === 0 ? 'Today' : this.dayLabel(d)))];
  });
  dotX(j: number) { return 18 + (j % 6) * ((this.colW - 30) / 5); }
  dotY(j: number) { return this.H - 52 - Math.floor(j / 6) * 15; }

  async load() {
    try {
      const before = this.room();
      const next = await this.api.get<Room>(`/workspaces/${this.ws}/control-room`);
      if (before?.available) {
        const seen = new Set(before.activity.map((a) => a.at + a.title + a.stage));
        this.fresh.set(new Set(next.activity.map((a) => a.at + a.title + a.stage).filter((k) => !seen.has(k))));
        this.timers.push(setTimeout(() => this.fresh.set(new Set()), 2500));
      }
      this.room.set(next);
      this.error.set('');
    } catch (e) { this.error.set(errorMessage(e)); }
  }

  open(p: Promise_) { this.router.navigate(['/projects', p.project_id, 'board']); }

  // ---------- live ----------
  private async connect() {
    this.source?.close();
    this.source = null;
    const ws = this.ws;
    if (!ws || typeof EventSource === 'undefined') return;
    this.live.set('connecting');
    let token: string;
    try { token = (await this.api.post<{ token: string }>(`/workspaces/${ws}/stream-token`)).token; }
    catch { this.reconnectLater(); return; }
    if (ws !== this.ws) return;
    const es = new EventSource(`${API_URL}/workspaces/${ws}/stream?token=${encodeURIComponent(token)}`);
    this.source = es;
    es.addEventListener('ready', () => { this.live.set('live'); this.retries = 0; });
    es.addEventListener('change', (e) => {
      ((JSON.parse((e as MessageEvent).data).task_ids ?? []) as string[]).forEach((id) => this.pendingIds.add(id));
      this.scheduleRefresh();
    });
    es.addEventListener('alert', (e) => {
      this.alerts.push(JSON.parse((e as MessageEvent).data).alert as Alert);  // forecast slips appear as toasts
      this.scheduleRefresh();
    });
    es.onerror = () => { if (this.source === es) { es.close(); this.source = null; this.reconnectLater(); } };
  }

  private reconnectLater() {
    this.live.set('connecting');
    this.timers.push(setTimeout(() => this.connect(), Math.min(30_000, 1000 * 2 ** this.retries++)));
  }

  /** Bursts of events refresh the page once. */
  private scheduleRefresh() {
    if (this.refreshTimer) return;
    this.refreshTimer = setTimeout(async () => {
      this.refreshTimer = null;
      const ids = new Set(this.pendingIds);
      this.pendingIds.clear();
      await this.load();
      this.flashed.set(ids);
      this.timers.push(setTimeout(() => this.flashed.set(new Set()), 2300));
    }, 600);
  }

  ngOnDestroy() {
    this.source?.close();
    this.timers.forEach(clearTimeout);
    if (this.refreshTimer) clearTimeout(this.refreshTimer);
    clearInterval(this.ticker);
  }

  // ---------- formatting ----------
  pct(v: number | null | undefined) { return v == null ? '–' : `${Math.round(v * 100)}%`; }
  noun(t: string) { return NOUNS[t] ?? 'items'; }
  stroke(t: string) { return STROKE[t] ?? 'stroke-info'; }
  text(t: string) { return TEXT[t] ?? 'text-info'; }
  label(stage: string) { const t = stage.replace(/_/g, ' '); return t.charAt(0).toUpperCase() + t.slice(1); }
  stageDot(stage: string) {
    if (['done', 'delivered', 'deployed', 'pr_merged'].includes(stage)) return 'bg-ok';
    if (['exception', 'rescheduled', 'blocked', 'deploy_failed', 'cancelled'].includes(stage)) return 'bg-bad';
    return 'bg-info';
  }
  dayLabel(iso: string) { return new Date(iso + 'T00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric' }); }
  dueText(p: Promise_) {
    if (p.when) {
      const d = new Date(p.when);
      return `${d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })}, ${d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false })}`;
    }
    const r = this.room();
    if (!p.due) return 'no date';
    if (r && p.due < r.days[0]) return `overdue since ${this.dayLabel(p.due)}`;
    return p.due === r?.days[0] ? 'due today' : `due ${this.dayLabel(p.due)}`;
  }
  ago(iso: string) {
    const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 60) return 'just now';
    if (s < 3600) return `${Math.round(s / 60)} min ago`;
    if (s < 86400) return `${Math.round(s / 3600)} h ago`;
    return `${Math.round(s / 86400)} days ago`;
  }
  private time() { return new Date().toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }); }
}
