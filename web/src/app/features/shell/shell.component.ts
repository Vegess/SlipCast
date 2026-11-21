import { Component, OnInit, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { Api, errorMessage } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { Project } from '../../core/models';
import { ThemeService } from '../../core/theme.service';
import { WorkspaceStore } from '../../core/workspace.store';
import { ImportDialog } from './import.dialog';
import { NewProjectDialog } from './new-project.dialog';

@Component({
  selector: 'app-shell',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, ImportDialog, NewProjectDialog],
  template: `
  <div class="flex h-full flex-col md:flex-row">
    <aside class="flex shrink-0 flex-col border-line bg-gradient-to-b from-panel to-panel-tint md:h-full md:w-64 md:border-r">
      <div class="px-3 pb-4 pt-4">
        @if (auth.workspaces().length > 1) {
          <label class="sr-only" for="workspace-picker">Workspace</label>
          <select id="workspace-picker" class="input bg-canvas/60 py-1.5 text-xs font-medium" (change)="switchTo($any($event.target).value)">
            @for (w of auth.workspaces(); track w.id) { <option [value]="w.id" [selected]="w.id === auth.workspace()?.id">{{ w.name }}</option> }
          </select>
        } @else {
          <p class="truncate px-2 text-xs font-medium text-muted">{{ auth.workspace()?.name }}</p>
        }
        @if (!auth.canEdit()) {
          <p class="anim-fade mt-2 rounded-lg bg-info/10 px-2.5 py-1.5 text-xs text-info-strong">View only. You can see everything here but not change it.</p>
        }
      </div>

      @if (auth.canEdit()) {
        <div class="grid grid-cols-2 gap-2 px-3">
          <button class="btn px-2" (click)="dialog.set('import')">Import CSV</button>
          <button class="btn px-2" (click)="loadDemo()" [disabled]="demoBusy()">{{ demoBusy() ? 'Loading…' : 'Demo data' }}</button>
        </div>
      }
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
        @if (auth.canEdit()) {
          <button class="flex shrink-0 items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-muted hover:bg-raised/60 hover:text-fg"
                  (click)="dialog.set('project')">+ New project</button>
        } @else if (!store.projects().length) {
          <p class="px-2.5 py-2 text-sm text-muted">No projects here yet.</p>
        }
      </nav>

      <div class="hidden space-y-3 border-t border-line px-5 py-4 md:block">
        <div class="flex items-center justify-between gap-2 text-sm">
          <span id="theme-label">Theme</span>
          <div class="flex gap-0.5 rounded-lg bg-canvas/70 p-0.5 ring-1 ring-line" role="radiogroup" aria-labelledby="theme-label">
            @for (t of themes; track t[0]) {
              <button type="button" role="radio" [attr.aria-checked]="theme.theme() === t[0]" (click)="theme.set(t[0])"
                      class="rounded-md px-2.5 py-1 text-xs font-medium"
                      [class.bg-raised]="theme.theme() === t[0]" [class.text-fg]="theme.theme() === t[0]" [class.text-muted]="theme.theme() !== t[0]">{{ t[1] }}</button>
            }
          </div>
        </div>
        <label class="flex cursor-pointer items-start gap-2.5 text-sm">
          <input type="checkbox" class="mt-1 accent-accent" [checked]="store.privacyMode()" (change)="store.setPrivacy($any($event.target).checked)">
          <span>Privacy mode<span class="block text-xs text-muted">Never send ticket titles or theme names to the AI.</span></span>
        </label>
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
  readonly theme = inject(ThemeService);
  readonly themes = [['dusk', 'Dusk'], ['light', 'Light']] as const;
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

  /** Projects belong to one workspace, so switching goes back to the project list. */
  switchTo(id: string) {
    this.auth.selectWorkspace(id);
    this.router.navigateByUrl('/projects');
  }

  async opened(p: Project) {
    this.dialog.set(null);
    await this.store.load();
    this.router.navigate(['/projects', p.id, 'board']);
  }
}
