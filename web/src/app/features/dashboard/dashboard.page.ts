import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Api, errorMessage } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { Project } from '../../core/models';
import { WorkspaceStore } from '../../core/workspace.store';
import { longDate } from '../../shared/format';

type Health = 'on_track' | 'at_risk' | 'off_track';
interface Card {
  project: Project;
  health: Health | null;
  open: number;
  forecastP85: string | null;
  forecastNote: string;
  highRisk: number | null;
  error: string;
}

const HEALTH: Record<Health, { label: string; cls: string }> = {
  on_track: { label: 'On track', cls: 'text-ok' },
  at_risk: { label: 'At risk', cls: 'text-accent' },
  off_track: { label: 'Off track', cls: 'text-bad' },
};

@Component({
  selector: 'app-dashboard',
  imports: [RouterLink],
  template: `
  <div class="mx-auto max-w-6xl px-4 py-8 sm:px-8">
    <h1 class="text-3xl font-bold">Hi {{ firstName() }}</h1>
    <p class="note mt-1">Every project at a glance: its health, open work, when it is 85% likely to finish, and how many tickets are likely to slip.</p>
    @if (error()) { <p class="mt-4 text-sm text-bad">{{ error() }}</p> }

    @if (loaded() && !cards().length) {
      <section class="card card-info mt-8 max-w-2xl">
        <h2 class="section-title">No projects yet</h2>
        <p class="note mt-1">Load six months of sample tickets to explore, or import a CSV export from Jira, GitHub Issues, Trello or Linear.</p>
        <div class="mt-4 flex flex-wrap gap-2">
          <button class="btn btn-primary" (click)="loadDemo()" [disabled]="busy() || !auth.canEdit()">{{ busy() ? 'Loading…' : 'Load demo data' }}</button>
          <a routerLink="/projects" class="btn">Import a CSV</a>
        </div>
      </section>
    }

    <div class="mt-8 grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
      @for (c of cards(); track c.project.id) {
        <a [routerLink]="['/projects', c.project.id, 'board']" class="card card-info block transition-colors hover:border-muted/60">
          <div class="flex items-start gap-2.5">
            <span class="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full" [style.background]="c.project.color"></span>
            <div class="min-w-0">
              <h2 class="truncate font-display text-lg font-medium">{{ c.project.name }}</h2>
              <p class="text-xs text-muted">{{ c.project.done_count }} of {{ c.project.task_count }} tickets done</p>
            </div>
          </div>
          @if (c.error) { <p class="mt-4 text-sm text-bad">{{ c.error }}</p> } @else {
            <dl class="mt-5 grid grid-cols-2 gap-x-4 gap-y-4">
              <div>
                <dt class="text-xs text-muted">Health</dt>
                <dd class="mt-0.5 font-display text-lg" [class]="c.health ? health[c.health].cls : 'text-muted'">{{ c.health ? health[c.health].label : '…' }}</dd>
              </div>
              <div>
                <dt class="text-xs text-muted">Open tickets</dt>
                <dd class="mt-0.5 font-display text-lg">{{ c.open }}</dd>
              </div>
              <div>
                <dt class="text-xs text-muted">85% likely done by</dt>
                <dd class="mt-0.5 font-display text-lg" [class.text-accent]="c.forecastP85">{{ c.forecastP85 ? longDate(c.forecastP85) : '—' }}</dd>
                @if (!c.forecastP85 && c.forecastNote) { <dd class="text-xs text-muted">{{ c.forecastNote }}</dd> }
              </div>
              <div>
                <dt class="text-xs text-muted">High slip risk</dt>
                <dd class="mt-0.5 font-display text-lg" [class.text-bad]="(c.highRisk ?? 0) > 0">{{ c.highRisk ?? '—' }}</dd>
                @if (c.highRisk === null) { <dd class="text-xs text-muted">Needs more finished tickets with due dates</dd> }
              </div>
            </dl>
          }
        </a>
      } @empty {
        @if (!loaded()) {
          @for (i of [1, 2, 3]; track i) { <div class="card h-48 animate-pulse bg-raised/40"></div> }
        }
      }
    </div>
  </div>`,
})
export class DashboardPage implements OnInit {
  private api = inject(Api);
  private store = inject(WorkspaceStore);
  readonly auth = inject(AuthService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  readonly health = HEALTH;
  readonly longDate = longDate;
  readonly cards = signal<Card[]>([]);
  readonly loaded = signal(false);
  readonly busy = signal(false);
  readonly error = signal('');

  firstName() { return this.auth.user()?.name.split(' ')[0] ?? ''; }

  async ngOnInit() {
    // "Try the demo" via Google or GitHub lands here with ?demo=1: open the demo project.
    if (this.route.snapshot.queryParamMap.get('demo') === '1' && this.auth.canEdit()) {
      try {
        const p = await this.api.post<Project>(`/workspaces/${this.store.workspaceId()}/demo-project`);
        await this.router.navigate(['/projects', p.id, 'board'], { replaceUrl: true });
        return;
      } catch (e) { this.error.set(errorMessage(e)); }
    }
    try {
      await this.store.load();
    } catch (e) { this.error.set(errorMessage(e)); }
    const projects = this.store.projects();
    this.cards.set(projects.map((p) => ({ project: p, health: null, open: p.task_count - p.done_count, forecastP85: null, forecastNote: '', highRisk: null, error: '' })));
    this.loaded.set(true);
    await Promise.all(projects.map((p) => this.fill(p)));
  }

  /**
   * Each card loads on its own, so one slow or failing project never blocks the rest.
   * Uses the overview endpoint (not /forecast) so visiting the dashboard doesn't add
   * entries to the forecast ledger; those are recorded when the Forecast tab is opened.
   */
  private async fill(p: Project) {
    const [health, overview] = await Promise.allSettled([
      this.api.get<{ health: Health; open_count: number }>(`/projects/${p.id}/insights`),
      this.api.get<{ open: number; forecast_p85: string | null; high_risk: number | null }>(`/projects/${p.id}/analytics/overview`),
    ]);
    this.cards.update((cs) => cs.map((c) => {
      if (c.project.id !== p.id) return c;
      const next = { ...c };
      if (health.status === 'fulfilled') next.health = health.value.health;
      if (overview.status === 'fulfilled') {
        next.open = overview.value.open;
        next.forecastP85 = overview.value.forecast_p85;
        next.highRisk = overview.value.high_risk;
        if (!next.forecastP85) next.forecastNote = next.open === 0 ? 'Everything is done' : 'Needs a few weeks of finished work';
      } else {
        next.forecastNote = 'Forecast not available yet';
      }
      if (health.status === 'rejected' && overview.status === 'rejected') next.error = errorMessage(health.reason);
      return next;
    }));
  }

  async loadDemo() {
    this.busy.set(true);
    try {
      await this.api.post(`/workspaces/${this.store.workspaceId()}/demo-project`);
      this.loaded.set(false);
      await this.ngOnInit();
    } catch (e) { this.error.set(errorMessage(e)); }
    finally { this.busy.set(false); }
  }
}
