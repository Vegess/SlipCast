import { Component, effect, inject, signal, untracked } from '@angular/core';
import { Api, errorMessage } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { ProjectContext } from './project.context';

interface GithubStatus {
  connected: boolean; repo: string | null; last_event_at: string | null;
  webhook_url: string; secret: string | null; events: string[];
}

/** Connect a GitHub repository: SlipCast shows the webhook URL and secret, GitHub does the rest. */
@Component({
  selector: 'app-github-connect',
  template: `
  <section class="card card-violet anim-rise">
    <div class="flex flex-wrap items-center gap-3">
      <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
        <circle cx="8" cy="7" r="3.5" class="stroke-info" stroke-width="2"/><circle cx="8" cy="21" r="3.5" class="stroke-info" stroke-width="2"/>
        <circle cx="21" cy="14" r="3.5" class="stroke-accent" stroke-width="2"/>
        <path d="M8 10.5v7M8 14c0-4 5-4 9.5 0" class="stroke-muted" stroke-width="2" stroke-linecap="round"/>
      </svg>
      <h2 class="section-title mr-auto">GitHub pull requests and releases</h2>
      @if (s(); as st) {
        @if (st.connected && st.last_event_at) {
          <span class="pill gap-1.5 bg-ok/15 text-ok-strong"><span class="live-dot bg-ok"></span>Receiving from {{ st.repo }}</span>
        } @else if (st.connected) {
          <span class="pill bg-accent/15 text-accent-strong">Waiting for GitHub's first delivery</span>
        } @else { <span class="pill bg-raised text-muted">Not connected</span> }
      }
    </div>
    <p class="note mt-2">GitHub tells SlipCast when pull requests are opened, reviewed and merged, and when releases and deployments happen.
      They appear on the Delivery tab with review times and the DORA metrics.</p>

    @if (s(); as st) {
      @if (!st.connected) {
        @if (auth.isAdmin()) {
          <button class="btn btn-primary mt-4" (click)="connect()" [disabled]="busy()">{{ busy() ? 'Setting up…' : 'Connect GitHub' }}</button>
        } @else { <p class="note mt-3">Ask a workspace admin to connect a repository.</p> }
      } @else {
        @if (st.last_event_at) { <p class="mt-3 text-xs text-muted">Last delivery {{ when(st.last_event_at) }}.</p> }
        @if (auth.isAdmin() && st.secret) {
          <ol class="mt-4 space-y-3 text-sm">
            <li><b>1.</b> In GitHub, open your repository → <b>Settings</b> → <b>Webhooks</b> → <b>Add webhook</b>.</li>
            <li><b>2. Payload URL</b>:
              <div class="mt-1 flex gap-2"><input class="input font-mono text-xs" [value]="st.webhook_url" readonly aria-label="Payload URL" (focus)="$any($event.target).select()">
                <button class="btn shrink-0" (click)="copy(st.webhook_url, 'url')">{{ copied() === 'url' ? 'Copied ✓' : 'Copy' }}</button></div></li>
            <li><b>3. Content type</b>: <code class="rounded bg-canvas px-1.5">application/json</code></li>
            <li><b>4. Secret</b>:
              <div class="mt-1 flex gap-2"><input class="input font-mono text-xs" [type]="reveal() ? 'text' : 'password'" [value]="st.secret" readonly aria-label="Webhook secret">
                <button class="btn shrink-0" (click)="reveal.set(!reveal())">{{ reveal() ? 'Hide' : 'Show' }}</button>
                <button class="btn shrink-0" (click)="copy(st.secret, 'secret')">{{ copied() === 'secret' ? 'Copied ✓' : 'Copy' }}</button></div></li>
            <li><b>5.</b> Choose <b>Let me select individual events</b> and tick <b>Pull requests</b>, <b>Pull request reviews</b>,
              <b>Releases</b> and <b>Deployment statuses</b>. Untick <b>Pushes</b>.</li>
            <li><b>6.</b> Click <b>Add webhook</b>. GitHub sends a test delivery and this card turns green.</li>
          </ol>
          <div class="mt-4 flex flex-wrap gap-2">
            <button class="btn" (click)="refresh()">Check again</button>
            <button class="btn btn-ghost text-muted" (click)="rotate()" [disabled]="busy()">New secret</button>
            <button class="btn btn-ghost text-muted" (click)="disconnect()" [disabled]="busy()">Disconnect</button>
          </div>
          <p class="mt-2 text-xs text-muted">Deployments come from GitHub Actions environments or any deploy tool that reports deployment statuses to GitHub.</p>
        }
      }
    }
    @if (error()) { <p class="mt-3 text-sm text-bad" role="alert">{{ error() }}</p> }
  </section>`,
})
export class GithubConnect {
  readonly auth = inject(AuthService);
  private ctx = inject(ProjectContext);
  private api = inject(Api);
  readonly s = signal<GithubStatus | null>(null);
  readonly busy = signal(false);
  readonly error = signal('');
  readonly reveal = signal(false);
  readonly copied = signal<'' | 'url' | 'secret'>('');

  constructor() {
    effect(() => { const id = this.ctx.id(); if (id) untracked(() => this.refresh()); });
    // A GitHub delivery arrived live: the status (repo, last delivery) has changed.
    effect(() => { if (this.ctx.activity().length) untracked(() => this.refresh()); });
  }

  async refresh() {
    try { this.s.set(await this.api.get<GithubStatus>(`/projects/${this.ctx.id()}/github`)); }
    catch (e) { this.error.set(errorMessage(e)); }
  }

  async connect() { await this.run(() => this.api.post<GithubStatus>(`/projects/${this.ctx.id()}/github`)); }

  async rotate() {
    if (!confirm('Make a new secret? GitHub deliveries fail until you paste the new secret into the webhook.')) return;
    await this.run(() => this.api.post<GithubStatus>(`/projects/${this.ctx.id()}/github`));
    this.reveal.set(true);
  }

  async disconnect() {
    if (!confirm('Disconnect GitHub? Past pull requests stay; new deliveries are refused.')) return;
    this.busy.set(true);
    try { await this.api.delete(`/projects/${this.ctx.id()}/github`); await this.refresh(); }
    catch (e) { this.error.set(errorMessage(e)); }
    finally { this.busy.set(false); }
  }

  private async run(call: () => Promise<GithubStatus>) {
    this.busy.set(true); this.error.set('');
    try { this.s.set(await call()); } catch (e) { this.error.set(errorMessage(e)); }
    finally { this.busy.set(false); }
  }

  async copy(text: string, what: 'url' | 'secret') {
    try { await navigator.clipboard.writeText(text); this.copied.set(what); setTimeout(() => this.copied.set(''), 2000); } catch { /* select manually */ }
  }

  when(iso: string): string {
    const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z');
    return d.toLocaleString([], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  }
}
