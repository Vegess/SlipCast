import { Component, computed, effect, inject, signal, untracked } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Api, errorMessage } from '../../core/api.service';
import { KIND_LABEL, STATUSES, Status, Task } from '../../core/models';
import { shortDate, todayISO } from '../../shared/format';
import { ProjectContext } from './project.context';
import { TaskDialog } from './task.dialog';

interface Health {
  health: 'on_track' | 'at_risk' | 'off_track'; completion: number; open_count: number;
  insights: { kind: string; severity: 'info' | 'warning' | 'critical'; message: string }[];
}

@Component({
  selector: 'app-board-view',
  imports: [FormsModule, TaskDialog],
  template: `
  @if (health(); as h) {
    <section class="mb-5 flex flex-wrap items-start gap-x-8 gap-y-3 rounded-xl border border-line bg-panel px-5 py-4">
      <div>
        <p class="text-xs text-muted">Project health</p>
        <p class="font-display text-2xl font-medium" [class.text-ok]="h.health === 'on_track'"
           [class.text-accent]="h.health === 'at_risk'" [class.text-bad]="h.health === 'off_track'">{{ healthLabel[h.health] }}</p>
        <p class="text-xs text-muted">{{ (h.completion * 100).toFixed(0) }}% complete · {{ h.open_count }} open</p>
      </div>
      <ul class="min-w-0 flex-1 space-y-1.5 text-sm">
        @for (i of h.insights.slice(0, 3); track i.kind) {
          <li class="flex gap-2"><span [class.text-bad]="i.severity === 'critical'" [class.text-accent]="i.severity === 'warning'" [class.text-info]="i.severity === 'info'">●</span><span>{{ i.message }}</span></li>
        } @empty { <li class="text-muted">Nothing overdue, blocked or unowned.</li> }
      </ul>
    </section>
  }
  <div class="mb-4 flex flex-wrap items-center gap-3">
    <input class="input max-w-xs" placeholder="Filter tickets…" [ngModel]="filter()" (ngModelChange)="filter.set($event)" aria-label="Filter tickets">
    <button class="btn ml-auto" (click)="open(null)">+ Add ticket</button>
  </div>
  @if (error()) { <p class="mb-3 text-sm text-bad">{{ error() }}</p> }
  <div class="flex gap-4 overflow-x-auto pb-2">
    @for (s of statuses; track s.id) {
      <section class="flex min-w-[250px] flex-1 flex-col" [attr.aria-label]="s.label">
        <header class="flex items-center gap-2 px-1 pb-2.5 text-sm font-semibold">
          <span class="h-3.5 w-[3px] rounded" [style.background]="s.color"></span>{{ s.label }}
          <span class="font-normal text-muted">{{ columns()[s.id].total }}</span>
        </header>
        <div class="flex min-h-[140px] flex-1 flex-col gap-2 rounded-xl bg-canvas/60 p-2 ring-1"
             [class.ring-info]="over() === s.id" [class.ring-line]="over() !== s.id"
             (dragover)="$event.preventDefault(); over.set(s.id)" (dragleave)="over.set(null)" (drop)="drop($event, s.id)">
          @for (t of columns()[s.id].items; track t.id) {
            <button draggable="true" (dragstart)="$event.dataTransfer?.setData('text/plain', t.id)" (click)="open(t)"
                    class="block w-full rounded-lg border border-line border-l-[3px] bg-panel px-3 py-2.5 text-left hover:border-muted/60"
                    [class.border-l-bad]="t.priority === 'high'" [class.border-l-accent]="t.priority === 'medium'">
              <span class="block text-sm font-medium leading-snug">{{ t.title }}</span>
              <span class="mt-1.5 flex flex-wrap gap-x-3 text-xs text-muted">
                <span>{{ t.owner || 'Unassigned' }}</span>
                @if (t.kind) { <span>{{ kindLabel[t.kind] }}</span> }
                <span [class.text-bad]="late(t)" [class.font-semibold]="late(t)">{{ late(t) ? 'Overdue · ' : '' }}{{ date(t.due) }}</span>
              </span>
            </button>
          }
          @if (columns()[s.id].total > columns()[s.id].items.length) {
            <p class="px-1 text-xs text-muted">Showing the {{ columns()[s.id].items.length }} most recent of {{ columns()[s.id].total }}.</p>
          }
          <input class="input mt-auto bg-transparent" placeholder="Quick add…" maxlength="140" [attr.aria-label]="'Quick add to ' + s.label"
                 (keydown.enter)="quickAdd($any($event.target), s.id)">
        </div>
      </section>
    }
  </div>
  @if (editing() !== undefined) {
    <app-task-dialog [task]="editing()!" (closed)="editing.set(undefined)" />
  }`,
})
export class BoardView {
  readonly ctx = inject(ProjectContext);
  private api = inject(Api);
  readonly health = signal<Health | null>(null);
  readonly healthLabel = { on_track: 'On track', at_risk: 'At risk', off_track: 'Off track' };

  constructor() {
    effect(() => {
      const id = this.ctx.id();
      this.ctx.version();
      if (!id) return;
      untracked(() => this.api.get<Health>(`/projects/${id}/insights`).then((h) => this.health.set(h)).catch(() => {}));
    });
  }

  readonly statuses = STATUSES;
  readonly kindLabel = KIND_LABEL;
  readonly filter = signal('');
  readonly over = signal<Status | null>(null);
  readonly editing = signal<Task | null | undefined>(undefined);
  readonly error = signal('');
  readonly date = shortDate;

  readonly columns = computed(() => {
    const q = this.filter().toLowerCase();
    const tasks = this.ctx.tasks().filter((t) => !q || t.title.toLowerCase().includes(q) || t.owner.toLowerCase().includes(q));
    const out = {} as Record<Status, { items: Task[]; total: number }>;
    for (const s of STATUSES) {
      let items = tasks.filter((t) => t.status === s.id);
      const total = items.length;
      if (s.id === 'done') items = [...items].sort((a, b) => (b.completed_at ?? '').localeCompare(a.completed_at ?? '')).slice(0, 30);
      else items = [...items].sort((a, b) => (a.due ?? '9999').localeCompare(b.due ?? '9999'));
      out[s.id] = { items, total };
    }
    return out;
  });

  late(t: Task) { return !!t.due && t.status !== 'done' && t.due < todayISO(); }
  open(t: Task | null) { this.editing.set(t); }

  drop(ev: DragEvent, status: Status) {
    ev.preventDefault();
    this.over.set(null);
    const id = ev.dataTransfer?.getData('text/plain');
    const t = this.ctx.tasks().find((x) => x.id === id);
    if (t && t.status !== status) this.ctx.updateTask(t.id, { status }).catch((e) => this.error.set(errorMessage(e)));
  }

  quickAdd(el: HTMLInputElement, status: Status) {
    const title = el.value.trim();
    if (!title) return;
    el.value = '';
    this.ctx.createTask({ title, status }).catch((e) => this.error.set(errorMessage(e)));
  }
}
