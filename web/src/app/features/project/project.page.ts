import { Component, effect, inject, input, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { errorMessage } from '../../core/api.service';
import { ProjectContext } from './project.context';
import { AuthService } from '../../core/auth.service';

@Component({
  selector: 'app-project-page',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  providers: [ProjectContext],
  template: `
  <div class="px-4 py-6 sm:px-8 sm:py-8">
    @if (error()) {
      <div class="mb-4 rounded-lg border border-bad/40 bg-bad/10 px-4 py-2.5 text-sm text-bad">{{ error() }}</div>
    }
    @if (ctx.project(); as p) {
      <header class="anim-fade mb-6 border-b border-line pb-5">
        <div class="flex flex-wrap items-start gap-4">
          <div class="min-w-0 flex-1">
            <input [value]="p.name" aria-label="Project name" maxlength="80" (keydown.enter)="$any($event.target).blur()" [readOnly]="!auth.canEdit()"
                   (blur)="rename($any($event.target).value)"
                   class="w-full max-w-3xl rounded-md bg-transparent font-display text-3xl font-bold hover:bg-raised/50 focus:bg-raised/50 focus:outline-none sm:text-4xl">
            <p class="mt-1 text-sm text-muted">
              @if (p.goal) { {{ p.goal }} · } {{ p.done_count }} of {{ p.task_count }} tickets done
              <span class="ml-2 inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 align-middle text-xs"
                    [class]="ctx.live() === 'live' ? 'bg-ok/10 text-ok-strong' : 'bg-raised text-muted'"
                    [title]="ctx.live() === 'live' ? 'This page updates by itself when anything changes' : 'Connecting to live updates'">
                <span class="live-dot" [class]="ctx.live() === 'live' ? 'bg-ok' : 'bg-muted'" aria-hidden="true"></span>
                {{ ctx.live() === 'live' ? 'Live' : 'Connecting…' }}
              </span>
            </p>
          </div>
          @if (auth.isAdmin()) { <button class="btn btn-ghost text-muted" (click)="remove()">Delete project</button> }
        </div>
        <nav class="-mb-5 mt-5 flex gap-1 overflow-x-auto" aria-label="Project views">
          @for (t of tabs; track t[0]) {
            <a [routerLink]="t[0]" routerLinkActive="tab-active !text-fg" ariaCurrentWhenActive="page"
               class="tab-link shrink-0 border-b-2 border-transparent px-3 pb-2.5 text-sm font-medium text-muted transition-colors hover:text-fg">{{ t[1] }}</a>
          }
        </nav>
      </header>
      <router-outlet />
    } @else if (!error()) {
      <div class="space-y-4" role="status" aria-label="Loading project">
        <div class="skeleton h-10 w-2/3 max-w-md"></div>
        <div class="skeleton h-4 w-1/3 max-w-xs"></div>
        <div class="skeleton mt-6 h-24 w-full"></div>
        <div class="grid gap-4 sm:grid-cols-4">
          @for (i of [0, 1, 2, 3]; track i) { <div class="skeleton h-48"></div> }
        </div>
      </div>
    }
  </div>`,
})
export class ProjectPage {
  readonly ctx = inject(ProjectContext);
  readonly auth = inject(AuthService);
  private router = inject(Router);
  readonly projectId = input.required<string>();
  readonly error = signal('');
  readonly tabs = [['board', 'Board'], ['delivery', 'Delivery'], ['forecast', 'Forecast'], ['text', 'Text insights'], ['advice', 'Advice'], ['evaluation', 'Model evaluation'], ['live', 'Live feed']] as const;

  constructor() {
    effect(() => {
      const id = this.projectId();
      this.error.set('');
      this.ctx.select(id).catch((e) => this.error.set(errorMessage(e)));
    });
  }

  rename(name: string) {
    if (!this.auth.canEdit()) return;
    const p = this.ctx.project();
    if (!p || !name.trim() || name.trim() === p.name) return;
    this.ctx.rename(name.trim()).catch((e) => this.error.set(errorMessage(e)));
  }

  async remove() {
    const p = this.ctx.project();
    if (!p || !confirm(`Delete "${p.name}" and its ${p.task_count} tickets?`)) return;
    try {
      await this.ctx.remove();
      this.router.navigateByUrl('/projects');
    } catch (e) { this.error.set(errorMessage(e)); }
  }
}
