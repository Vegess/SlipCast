import { Component, effect, inject, signal, untracked } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Alert } from '../../core/alerts.service';
import { Api, errorMessage } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { API_URL } from '../../core/config';
import { prefersReducedMotion } from '../../shared/motion';
import { GithubConnect } from './github-connect.component';
import { ProjectContext } from './project.context';

interface Stage { key: string; label: string; category: 'todo' | 'doing' | 'blocked' | 'done'; }
interface ApiKey { id: string; name: string; prefix: string; created_at: string; last_used_at: string | null; key: string | null; }

const CATEGORY = {
  todo: { label: 'Not started', cls: 'bg-raised text-muted' },
  doing: { label: 'In progress', cls: 'bg-info/15 text-info-strong' },
  blocked: { label: 'Blocked', cls: 'bg-bad/15 text-bad-strong' },
  done: { label: 'Done', cls: 'bg-ok/15 text-ok-strong' },
};

@Component({
  selector: 'app-live-view',
  imports: [FormsModule, GithubConnect],
  template: `
  <p class="note mb-5">Send stage changes from another system (an order app, a courier feed, a script) and every open
    screen updates within seconds. SlipCast re-runs the forecast and raises an alert when something matters.</p>

  <!-- How an event travels: drawn live, and it flashes when a real event arrives. -->
  <section class="card card-info anim-rise overflow-hidden">
    <h2 class="section-title">How live updates flow</h2>
    <p class="note mt-1">Each dot is an event: checked against your key, applied to the item, then the board, forecast and alerts update.</p>
    <svg viewBox="0 0 720 230" class="mt-4 w-full" role="img" aria-label="Your system sends events to the SlipCast API, which updates the board, the forecast and alerts">
      <defs>
        <path id="lf-in" d="M178 115 H272"/>
        <path id="lf-board" d="M448 115 C500 115 505 45 556 45"/>
        <path id="lf-fc" d="M448 115 H556"/>
        <path id="lf-alert" d="M448 115 C500 115 505 185 556 185"/>
        <radialGradient id="lf-glow"><stop offset="0" style="stop-color: rgb(var(--c-accent))" stop-opacity=".55"/><stop offset="1" style="stop-color: rgb(var(--c-accent))" stop-opacity="0"/></radialGradient>
      </defs>
      @for (p of ['lf-in', 'lf-board', 'lf-fc', 'lf-alert']; track p) {
        <use [attr.href]="'#' + p" fill="none" class="stroke-line" stroke-width="2"/>
        <use [attr.href]="'#' + p" fill="none" class="flow-line stroke-info/60" stroke-width="2"/>
      }
      <!-- source -->
      <g>
        <rect x="18" y="72" width="160" height="86" rx="14" class="fill-raised stroke-line" stroke-width="1.5"/>
        <text x="98" y="106" text-anchor="middle" class="fill-fg text-[14px] font-medium">Your system</text>
        <text x="98" y="127" text-anchor="middle" class="fill-muted text-[11px]">order app, courier feed,</text>
        <text x="98" y="142" text-anchor="middle" class="fill-muted text-[11px]">CI pipeline or script</text>
      </g>
      <!-- engine -->
      <g>
        <circle cx="360" cy="115" r="84" fill="url(#lf-glow)" [class.burst]="burst()" class="engine-glow" opacity="0"/>
        <rect x="272" y="62" width="176" height="106" rx="16" class="fill-panel stroke-accent/70" stroke-width="1.8"/>
        <text x="360" y="96" text-anchor="middle" class="fill-fg text-[14px] font-semibold">SlipCast</text>
        <text x="360" y="117" text-anchor="middle" class="fill-muted text-[11px]">checks the key</text>
        <text x="360" y="133" text-anchor="middle" class="fill-muted text-[11px]">ignores repeats</text>
        <text x="360" y="149" text-anchor="middle" class="fill-muted text-[11px]">re-runs the forecast</text>
      </g>
      <!-- outputs -->
      @for (o of outputs; track o.label) {
        <g>
          <rect x="556" [attr.y]="o.y - 24" width="148" height="48" rx="12" class="fill-raised stroke-line" stroke-width="1.5"/>
          <circle cx="578" [attr.cy]="o.y" r="5" [attr.class]="o.dot"/>
          <text x="592" [attr.y]="o.y + 4" class="fill-fg text-[13px]">{{ o.label }}</text>
        </g>
      }
      <!-- travelling events (static under reduced motion) -->
      @if (!reduced) {
        @for (d of dots; track $index) {
          <circle r="4.5" [attr.class]="d.cls">
            <animateMotion [attr.dur]="d.dur" repeatCount="indefinite" [attr.begin]="d.begin" rotate="auto">
              <mpath [attr.href]="'#' + d.path"/>
            </animateMotion>
          </circle>
        }
      }
    </svg>
  </section>

  <div class="mt-5 grid gap-5 lg:grid-cols-[1.15fr_1fr]">
    <section class="card card-violet anim-rise" style="--i: 1">
      <h2 class="section-title">Send an event</h2>
      <p class="note mt-1">One event, or <code class="text-fg">{{ '{' }}"events": [...]{{ '}' }}</code> with up to 500. Unknown items are created; the same event twice changes nothing.</p>
      <div class="mt-3 flex gap-1 rounded-lg bg-canvas/70 p-0.5 text-xs ring-1 ring-line" role="tablist" aria-label="Example language">
        @for (s of shells; track s[0]) {
          <button role="tab" class="flex-1 rounded-md px-2 py-1 font-medium" [attr.aria-selected]="shell() === s[0]"
                  [class.bg-raised]="shell() === s[0]" [class.text-fg]="shell() === s[0]" [class.text-muted]="shell() !== s[0]"
                  (click)="shell.set(s[0])">{{ s[1] }}</button>
        }
      </div>
      <div class="relative mt-3">
        <pre class="max-h-72 overflow-auto rounded-lg bg-canvas p-3 text-xs leading-relaxed"><code>{{ example() }}</code></pre>
        <button class="btn absolute right-2 top-2 px-2 py-1 text-xs" (click)="copy(example(), 'example')">{{ copied() === 'example' ? 'Copied ✓' : 'Copy' }}</button>
      </div>
      <p class="mt-2 text-xs text-muted">Fields: <b>external_id</b> and <b>stage</b> are required; <b>occurred_at</b> (defaults to now), title, description, owner, due, priority, kind and attributes are optional.</p>
    </section>

    <section class="card anim-rise" style="--i: 2">
      <h2 class="section-title">This project's stages</h2>
      <p class="note mt-1">Use these keys as <b>stage</b>. Each one counts as one of four states in the forecast.</p>
      <ul class="mt-3 divide-y divide-line/70 text-sm">
        @for (s of stages(); track s.key; let i = $index) {
          <li class="anim-rise flex items-center gap-3 py-2" [style.--i]="i">
            <code class="rounded bg-canvas px-1.5 py-0.5 text-xs">{{ s.key }}</code>
            <span class="flex-1">{{ s.label }}</span>
            <span class="pill" [class]="category[s.category].cls">{{ category[s.category].label }}</span>
          </li>
        }
      </ul>
    </section>
  </div>

  <div class="mt-5"><app-github-connect /></div>

  <section class="card card-accent anim-rise mt-5" style="--i: 3">
    <h2 class="section-title">API keys</h2>
    @if (auth.isAdmin()) {
      <p class="note mt-1">A key lets one system send events to this project only. Keep it secret, like a password.</p>
      <form class="mt-4 flex flex-wrap items-end gap-3" (ngSubmit)="createKey()">
        <label class="label">Name <input class="input w-64" name="keyName" [(ngModel)]="keyName" maxlength="60" placeholder="e.g. Order system"></label>
        <button class="btn btn-primary" [disabled]="busy() || !keyName.trim()">{{ busy() ? 'Creating…' : 'Create key' }}</button>
      </form>
      @if (fresh(); as k) {
        <div class="anim-pop mt-4 rounded-lg border border-accent/50 bg-accent/10 p-3">
          <p class="text-sm font-medium">Copy this key now. For security it won't be shown again.</p>
          <div class="mt-2 flex gap-2">
            <input class="input font-mono text-xs" [value]="k.key" readonly (focus)="$any($event.target).select()" aria-label="New API key">
            <button class="btn shrink-0" (click)="copy(k.key!, 'key')">{{ copied() === 'key' ? 'Copied ✓' : 'Copy' }}</button>
          </div>
        </div>
      }
      <ul class="mt-4 divide-y divide-line/70 text-sm">
        @for (k of keys(); track k.id) {
          <li class="flex flex-wrap items-center gap-3 py-2.5">
            <span class="font-medium">{{ k.name }}</span>
            <code class="text-xs text-muted">{{ k.prefix }}…</code>
            <span class="flex-1 text-xs text-muted">{{ k.last_used_at ? 'Last used ' + when(k.last_used_at) : 'Not used yet' }}</span>
            <button class="btn btn-ghost px-2 text-muted" (click)="revoke(k)">Revoke</button>
          </li>
        } @empty { <li class="py-2 text-sm text-muted">No keys yet.</li> }
      </ul>
    } @else {
      <p class="note mt-1">Only workspace admins can create keys. Ask an admin if another system should send events here.</p>
    }
    @if (error()) { <p class="mt-3 text-sm text-bad" role="alert">{{ error() }}</p> }
  </section>

  <div class="mt-5 grid gap-5 lg:grid-cols-2">
    <section class="card anim-rise" style="--i: 4">
      <h2 class="section-title">Arrived while you were here</h2>
      <p class="note mt-1">Everything this page heard live since you opened the project.</p>
      <ul class="mt-3 space-y-2 text-sm">
        @for (a of ctx.activity(); track a.at.getTime() + a.text) {
          <li class="anim-rise flex gap-2.5"><span class="mt-1.5 h-2 w-2 shrink-0 rounded-full" [class.bg-info]="a.kind === 'change'" [class.bg-accent]="a.kind === 'alert'"></span>
            <span class="flex-1">{{ a.text }}</span><span class="text-xs text-muted">{{ a.at.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) }}</span></li>
        } @empty { <li class="text-muted">Nothing yet. Send an event and watch it appear here and on the board.</li> }
      </ul>
    </section>
    <section class="card anim-rise" style="--i: 5">
      <h2 class="section-title">Alerts for this project</h2>
      <p class="note mt-1">Raised when the 85% finish date moves by 2 days or more, or new work looks likely to slip.</p>
      <ul class="mt-3 space-y-2.5 text-sm">
        @for (a of alerts(); track a.id) {
          <li class="flex gap-2.5"><span class="mt-1.5 h-2 w-2 shrink-0 rounded-full" [class.bg-bad]="a.severity === 'critical'" [class.bg-accent]="a.severity === 'warning'" [class.bg-info]="a.severity === 'info'"></span>
            <span class="flex-1">{{ a.message }}</span><span class="shrink-0 text-xs text-muted">{{ when(a.created_at) }}</span></li>
        } @empty { <li class="text-muted">No alerts yet.</li> }
      </ul>
    </section>
  </div>`,
})
export class LiveView {
  readonly ctx = inject(ProjectContext);
  readonly auth = inject(AuthService);
  private api = inject(Api);
  readonly reduced = prefersReducedMotion();
  readonly category = CATEGORY;
  readonly stages = signal<Stage[]>([]);
  readonly keys = signal<ApiKey[]>([]);
  readonly alerts = signal<Alert[]>([]);
  readonly fresh = signal<ApiKey | null>(null);
  readonly busy = signal(false);
  readonly error = signal('');
  readonly copied = signal<'' | 'key' | 'example'>('');
  readonly burst = signal(false);
  readonly shell = signal<'bash' | 'powershell'>('bash');
  readonly shells = [['bash', 'curl (Mac, Linux, Git Bash)'], ['powershell', 'PowerShell (Windows)']] as const;
  keyName = '';
  readonly outputs = [
    { label: 'Board', y: 45, dot: 'fill-info' },
    { label: 'Forecast', y: 115, dot: 'fill-accent' },
    { label: 'Alerts', y: 185, dot: 'fill-bad' },
  ];
  readonly dots = [
    { path: 'lf-in', dur: '1.6s', begin: '0s', cls: 'fill-info' },
    { path: 'lf-in', dur: '1.6s', begin: '0.8s', cls: 'fill-info' },
    { path: 'lf-board', dur: '1.8s', begin: '0.4s', cls: 'fill-info' },
    { path: 'lf-fc', dur: '1.5s', begin: '0.9s', cls: 'fill-accent' },
    { path: 'lf-alert', dur: '2.1s', begin: '1.3s', cls: 'fill-bad' },
  ];

  constructor() {
    effect(() => {
      const id = this.ctx.id();
      if (!id) return;
      untracked(() => this.load(id));
    });
    // A real event just arrived: the engine node flashes and the alert list refreshes.
    let first = true;
    effect(() => {
      this.ctx.activity();
      if (first) { first = false; return; }
      untracked(() => {
        this.burst.set(false);
        requestAnimationFrame(() => this.burst.set(true));
        setTimeout(() => this.burst.set(false), 900);
        this.loadAlerts(this.ctx.id());
      });
    });
  }

  private async load(id: string) {
    this.fresh.set(null);
    try { this.stages.set((await this.api.get<{ stages: Stage[] }>(`/projects/${id}/stages`)).stages); } catch (e) { this.error.set(errorMessage(e)); }
    this.loadAlerts(id);
    if (this.auth.isAdmin()) this.api.get<ApiKey[]>(`/projects/${id}/api-keys`).then((k) => this.keys.set(k)).catch(() => {});
  }

  private loadAlerts(id: string) {
    this.api.get<Alert[]>(`/projects/${id}/alerts`).then((a) => this.alerts.set(a)).catch(() => {});
  }

  example(): string {
    const url = `${API_URL}/projects/${this.ctx.id()}/events`;
    const stage = this.stages()[1]?.key ?? 'in_progress';
    const due = new Date(Date.now() + 5 * 864e5).toISOString().slice(0, 10);
    const key = this.fresh()?.key ?? 'YOUR_API_KEY';
    const body = `{"external_id": "ORDER-1042", "stage": "${stage}", "title": "Order 1042 for Asha", "due": "${due}"}`;
    if (this.shell() === 'powershell') {
      return `Invoke-RestMethod -Method Post -Uri "${url}" \`\n  -Headers @{ "X-SlipCast-Key" = "${key}" } \`\n  -ContentType "application/json" \`\n  -Body '${body}'`;
    }
    return `curl -X POST "${url}" \\\n  -H "X-SlipCast-Key: ${key}" \\\n  -H "Content-Type: application/json" \\\n  -d '${body}'`;
  }

  async createKey() {
    this.busy.set(true); this.error.set('');
    try {
      const k = await this.api.post<ApiKey>(`/projects/${this.ctx.id()}/api-keys`, { name: this.keyName.trim() });
      this.fresh.set(k); this.keyName = '';
      this.keys.set(await this.api.get<ApiKey[]>(`/projects/${this.ctx.id()}/api-keys`));
    } catch (e) { this.error.set(errorMessage(e)); }
    finally { this.busy.set(false); }
  }

  async revoke(k: ApiKey) {
    if (!confirm(`Revoke "${k.name}"? Anything using it stops being able to send events.`)) return;
    try {
      await this.api.delete(`/projects/${this.ctx.id()}/api-keys/${k.id}`);
      this.keys.update((ks) => ks.filter((x) => x.id !== k.id));
      if (this.fresh()?.id === k.id) this.fresh.set(null);
    } catch (e) { this.error.set(errorMessage(e)); }
  }

  async copy(text: string, what: 'key' | 'example') {
    try { await navigator.clipboard.writeText(text); this.copied.set(what); setTimeout(() => this.copied.set(''), 2000); } catch { /* select manually */ }
  }

  when(iso: string): string {
    const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z');
    return d.toLocaleString([], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  }
}
