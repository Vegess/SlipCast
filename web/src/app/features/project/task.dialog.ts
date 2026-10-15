import { Component, OnInit, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { errorMessage } from '../../core/api.service';
import { KIND_LABEL, STATUSES, Task } from '../../core/models';
import { ModalComponent } from '../../shared/modal.component';
import { ProjectContext } from './project.context';

@Component({
  selector: 'app-task-dialog',
  imports: [FormsModule, ModalComponent],
  template: `
  <app-modal [heading]="task() ? 'Ticket' : 'New ticket'"  (closed)="closed.emit()">
    <div class="grid gap-6">
      <form id="task-form" class="grid content-start gap-4" (ngSubmit)="save()">
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

    </div>

    <ng-container footer>
      @if (task()) { <button class="btn btn-ghost mr-auto text-bad" (click)="remove()">Delete</button> }
      <button class="btn" (click)="closed.emit()">Cancel</button>
      <button class="btn btn-primary" form="task-form" [disabled]="saving()">{{ saving() ? 'Saving…' : 'Save' }}</button>
    </ng-container>
  </app-modal>`,
})
export class TaskDialog implements OnInit {
  private ctx = inject(ProjectContext);
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
