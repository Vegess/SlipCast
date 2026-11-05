import { Component, effect, inject, input, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { errorMessage } from '../../core/api.service';
import { ProjectContext } from './project.context';

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
      <header class="mb-6 border-b border-line pb-5">
        <div class="flex flex-wrap items-start gap-4">
          <div class="min-w-0 flex-1">
            <input [value]="p.name" aria-label="Project name" maxlength="80" (keydown.enter)="$any($event.target).blur()"
                   (blur)="rename($any($event.target).value)"
                   class="w-full max-w-3xl rounded-md bg-transparent font-display text-3xl font-bold hover:bg-raised/50 focus:bg-raised/50 focus:outline-none sm:text-4xl">
            <p class="mt-1 text-sm text-muted">
              @if (p.goal) { {{ p.goal }} · } {{ p.done_count }} of {{ p.task_count }} tickets done
            </p>
          </div>
          <button class="btn btn-ghost text-muted" (click)="remove()">Delete project</button>
        </div>
        <nav class="-mb-5 mt-5 flex gap-1 overflow-x-auto" aria-label="Project views">
          @for (t of tabs; track t[0]) {
            <a [routerLink]="t[0]" routerLinkActive="!border-accent !text-fg" ariaCurrentWhenActive="page"
               class="shrink-0 border-b-2 border-transparent px-3 pb-2.5 text-sm font-medium text-muted hover:text-fg">{{ t[1] }}</a>
          }
        </nav>
      </header>
      <router-outlet />
    } @else if (!error()) {
      <p class="note">Loading project…</p>
    }
  </div>`,
})
export class ProjectPage {
  readonly ctx = inject(ProjectContext);
  private router = inject(Router);
  readonly projectId = input.required<string>();
  readonly error = signal('');
  readonly tabs = [['board', 'Board'], ['delivery', 'Delivery'], ['forecast', 'Forecast'], ['text', 'Text insights'], ['advice', 'Advice'], ['evaluation', 'Model evaluation']] as const;

  constructor() {
    effect(() => {
      const id = this.projectId();
      this.error.set('');
      this.ctx.select(id).catch((e) => this.error.set(errorMessage(e)));
    });
  }

  rename(name: string) {
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
