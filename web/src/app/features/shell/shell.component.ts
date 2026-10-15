import { Component, OnInit, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { Api, errorMessage } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { Project } from '../../core/models';
import { WorkspaceStore } from '../../core/workspace.store';
import { ImportDialog } from './import.dialog';
import { NewProjectDialog } from './new-project.dialog';

@Component({
  selector: 'app-shell',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, ImportDialog, NewProjectDialog],
  template: `
  <div class="flex h-full flex-col md:flex-row">
    <aside class="flex shrink-0 flex-col border-line bg-panel md:h-full md:w-64 md:border-r">
      <a routerLink="/" class="flex items-center gap-2.5 px-5 pb-1 pt-5">
        <img src="favicon.svg" alt="" width="26" height="26">
        <span class="font-display text-xl font-bold">Plotline</span>
      </a>
      <p class="truncate px-5 pb-4 text-xs text-muted">{{ auth.workspace()?.name }}</p>

      <div class="grid grid-cols-2 gap-2 px-3">
        <button class="btn px-2" (click)="dialog.set('import')">Import CSV</button>
        <button class="btn px-2" (click)="loadDemo()" [disabled]="demoBusy()">{{ demoBusy() ? 'Loading…' : 'Demo data' }}</button>
      </div>
      @if (error()) { <p class="px-4 pt-2 text-xs text-bad">{{ error() }}</p> }

      <nav aria-label="Projects" class="mt-4 flex gap-1 overflow-x-auto px-3 pb-2 md:flex-1 md:flex-col md:overflow-y-auto">
        <span class="hidden px-2 pb-1 text-xs font-medium text-muted md:block">Projects</span>
        @for (p of store.projects(); track p.id) {
          <a [routerLink]="['/projects', p.id]" routerLinkActive="bg-raised !text-fg"
             class="flex shrink-0 items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-fg/80 hover:bg-raised/60">
            <span class="h-2.5 w-2.5 shrink-0 rounded-full" [style.background]="p.color"></span>
            <span class="truncate whitespace-nowrap md:whitespace-normal">{{ p.name }}</span>
            <span class="ml-auto hidden text-xs text-muted md:inline">{{ p.task_count - p.done_count }}</span>
          </a>
        }
        <button class="flex shrink-0 items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-muted hover:bg-raised/60 hover:text-fg"
                (click)="dialog.set('project')">+ New project</button>
      </nav>

      <div class="hidden space-y-3 border-t border-line px-5 py-4 md:block">
        <div class="flex items-center justify-between">
          <span class="truncate text-sm">{{ auth.user()?.name }}</span>
          <button class="btn btn-ghost px-2 text-xs text-muted" (click)="auth.logout()">Sign out</button>
        </div>
      </div>
    </aside>

    <main class="min-w-0 flex-1 overflow-y-auto"><router-outlet /></main>
  </div>

  @if (dialog() === 'import') { <app-import-dialog (closed)="dialog.set(null)" (imported)="opened($event)" /> }
  @if (dialog() === 'project') { <app-new-project-dialog (closed)="dialog.set(null)" (created)="opened($event)" /> }
  `,
})
export class ShellComponent implements OnInit {
  readonly auth = inject(AuthService);
  readonly store = inject(WorkspaceStore);
  private api = inject(Api);
  private router = inject(Router);
  readonly dialog = signal<'import' | 'project' | null>(null);
  readonly demoBusy = signal(false);
  readonly error = signal('');

  ngOnInit() { this.store.load().catch((e) => this.error.set(errorMessage(e))); }

  async loadDemo() {
    this.demoBusy.set(true);
    this.error.set('');
    try {
      const p = await this.api.post<Project>(`/workspaces/${this.store.workspaceId()}/demo-project`);
      await this.opened(p);
    } catch (e) {
      this.error.set(errorMessage(e));
    } finally {
      this.demoBusy.set(false);
    }
  }

  async opened(p: Project) {
    this.dialog.set(null);
    await this.store.load();
    this.router.navigate(['/projects', p.id, 'board']);
  }
}
