import { Component, OnDestroy, OnInit, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Api, errorMessage } from '../../core/api.service';
import { KIND_LABEL, STATUSES, Task, TicketCheck } from '../../core/models';
import { ModalComponent } from '../../shared/modal.component';
import { ProjectContext } from './project.context';

@Component({
  selector: 'app-task-dialog',
  imports: [FormsModule, ModalComponent],
  template: `
  <app-modal [heading]="task() ? 'Ticket' : 'New ticket'" [wide]="true" (closed)="closed.emit()">
    <div class="grid gap-6 sm:grid-cols-[minmax(0,1fr)_260px]">
      <form id="task-form" class="grid content-start gap-4" (ngSubmit)="save()" (input)="schedule()" (change)="schedule()">
        <label class="label">Title <input class="input" name="title" [(ngModel)]="form.title" maxlength="140" required></label>
        <label class="label">Description <textarea class="input min-h-[120px]" name="description" [(ngModel)]="form.description" maxlength="5000"></textarea></label>
        <div class="grid gap-4 sm:grid-cols-2">
          <label class="label">Owner <input class="input" name="owner" [(ngModel)]="form.owner" maxlength="40"></label>
          <label class="label">Due date <input class="input" type="date" name="due" [(ngModel)]="form.due"></label>
          <label class="label">Status
            <select class="input" name="status" [(ngModel)]="form.status">@for (s of statuses; track s.id) { <option [value]="s.id">{{ s.label }}</option> }</select>
          </label>
          <label class="label">Priority
            <select class="input" name="priority" [(ngModel)]="form.priority"><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select>
          </label>
          <label class="label">Type
            <select class="input" name="kind" [(ngModel)]="form.kind">
              <option [ngValue]="null">Not set</option>
              @for (k of kinds; track k) { <option [value]="k">{{ kindLabel[k] }}</option> }
            </select>
          </label>
        </div>
        @if (error()) { <p class="text-sm text-bad">{{ error() }}</p> }
      </form>

      <aside class="flex min-w-0 flex-col gap-4 self-start rounded-xl border border-line bg-canvas/60 p-4 text-sm" aria-live="polite" aria-label="Ticket check">
        <div>
          <p class="text-xs font-medium uppercase tracking-wide text-muted">Ticket check</p>
          <p class="mt-1 text-xs text-muted">Compared with this project's history as you type. It never blocks saving.</p>
        </div>
        @if (check(); as c) {
          <div>
            <p class="flex items-baseline gap-2"><span class="font-display text-3xl" [class.text-bad]="c.quality.score < 50" [class.text-accent]="c.quality.score >= 50 && c.quality.score < 80" [class.text-ok]="c.quality.score >= 80">{{ c.quality.score }}</span><span class="text-muted">/100 ready to work on</span></p>
            @if (c.quality.reasons.length) {
              <ul class="mt-1.5 list-disc space-y-0.5 pl-4 text-xs text-muted">@for (r of c.quality.reasons; track r) { <li>{{ r }}</li> }</ul>
            }
          </div>
          <div>
            <p class="text-xs font-medium text-muted">How long tickets like this really took</p>
            @if (c.reference.available) {
              <p class="mt-1 font-medium">{{ c.reference.summary }}</p>
              @if (c.reference.plan?.planned_days !== null && c.reference.plan) {
                <p class="mt-1 text-xs" [class.text-bad]="c.reference.plan.under_planned" [class.text-muted]="!c.reference.plan.under_planned">{{ c.reference.plan.message }}</p>
              }
              <ul class="mt-2 space-y-1 text-xs text-muted">
                @for (s of c.reference.similar; track s.id) { <li class="flex gap-2"><span class="w-10 shrink-0 text-fg">{{ s.days }}d</span><span class="truncate" [title]="s.title">{{ s.title }}</span></li> }
              </ul>
            } @else { <p class="mt-1 text-xs text-muted">{{ c.reference.reason }}</p> }
          </div>
          @if (c.slip_risk) {
            <div>
              <p class="text-xs font-medium text-muted">Chance of missing the due date</p>
              <p class="mt-1 font-display text-2xl" [class.text-bad]="c.slip_risk.risk >= .6" [class.text-accent]="c.slip_risk.risk >= .35 && c.slip_risk.risk < .6" [class.text-ok]="c.slip_risk.risk < .35">{{ (c.slip_risk.risk * 100).toFixed(0) }}%</p>
              @if (c.slip_risk.factors.length) { <p class="text-xs text-muted">{{ c.slip_risk.factors.join(' · ') }}</p> }
            </div>
          }
          @if (c.duplicates.length) {
            <div>
              <p class="text-xs font-medium text-accent">Possible duplicates</p>
              <ul class="mt-1 space-y-1 text-xs">@for (d of c.duplicates; track d.id) { <li>{{ (d.similarity * 100).toFixed(0) }}% · {{ d.title }} <span class="text-muted">({{ d.status }})</span></li> }</ul>
            </div>
          }
        } @else { <p class="text-xs text-muted">{{ checkError() || 'Start typing to check this ticket.' }}</p> }
      </aside>
    </div>

    <ng-container footer>
      @if (task()) { <button class="btn btn-ghost mr-auto text-bad" (click)="remove()">Delete</button> }
      <button class="btn" (click)="closed.emit()">Cancel</button>
      <button class="btn btn-primary" form="task-form" [disabled]="saving()">{{ saving() ? 'Saving…' : 'Save' }}</button>
    </ng-container>
  </app-modal>`,
})
export class TaskDialog implements OnInit, OnDestroy {
  private ctx = inject(ProjectContext);
  private api = inject(Api);
  private timer: ReturnType<typeof setTimeout> | undefined;
  private seq = 0;
  readonly check = signal<TicketCheck | null>(null);
  readonly checkError = signal('');
  readonly task = input<Task | null>(null);
  readonly closed = output<void>();
  readonly statuses = STATUSES;
  readonly kinds = ['bug', 'feature', 'tech_debt', 'support'];
  readonly kindLabel = KIND_LABEL;
  readonly saving = signal(false);
  readonly error = signal('');
  form = { title: '', description: '', owner: '', due: '', status: 'planned', priority: 'medium', kind: null as string | null };

  ngOnInit() {
    const t = this.task();
    if (t) {
      this.form = { title: t.title, description: t.description, owner: t.owner, due: t.due ?? '', status: t.status,
        priority: t.priority, kind: t.kind_source === 'label' ? t.kind : null };
    }
    this.runCheck();
  }

  ngOnDestroy() { clearTimeout(this.timer); this.seq++; }

  /** Debounced write-time check: waits 600 ms after the last keystroke. */
  schedule() {
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.runCheck(), 600);
  }

  private async runCheck() {
    const seq = ++this.seq;
    const f = this.form;
    try {
      const r = await this.api.post<TicketCheck>(`/projects/${this.ctx.id()}/ticket-check`, {
        title: f.title, description: f.description, owner: f.owner, due: f.due || null, priority: f.priority,
        kind: f.kind || null, task_id: this.task()?.id ?? null,
      });
      if (seq === this.seq) { this.check.set(r); this.checkError.set(''); }
    } catch (e) {
      if (seq === this.seq) this.checkError.set(errorMessage(e));
    }
  }

  async save() {
    if (!this.form.title.trim()) { this.error.set('Add a title to save the ticket.'); return; }
    this.saving.set(true);
    const body: Record<string, unknown> = { ...this.form, due: this.form.due || null };
    if (!body['kind']) delete body['kind'];
    try {
      const t = this.task();
      if (t) await this.ctx.updateTask(t.id, body as Partial<Task>);
      else await this.ctx.createTask(body as Partial<Task>);
      this.closed.emit();
    } catch (e) {
      this.error.set(errorMessage(e));
      this.saving.set(false);
    }
  }

  async remove() {
    try { await this.ctx.deleteTask(this.task()!.id); this.closed.emit(); }
    catch (e) { this.error.set(errorMessage(e)); }
  }
}
