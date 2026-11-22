import { Component, inject, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Api, errorMessage } from '../../core/api.service';
import { Project } from '../../core/models';
import { WorkspaceStore } from '../../core/workspace.store';
import { ModalComponent } from '../../shared/modal.component';

@Component({
  selector: 'app-new-project-dialog',
  imports: [FormsModule, ModalComponent],
  template: `
  <app-modal heading="New project" (closed)="closed.emit()">
    <form id="project-form" class="grid gap-4" (ngSubmit)="save()">
      <label class="label">Project name <input class="input" name="name" [(ngModel)]="name" maxlength="80" required placeholder="e.g. Billing v2"></label>
      <label class="label">Goal <input class="input" name="goal" [(ngModel)]="goal" maxlength="300" placeholder="One line on the outcome"></label>
      <fieldset>
        <legend class="label">What will you track?</legend>
        <div class="mt-1.5 grid gap-2" role="radiogroup">
          @for (m of modules; track m.id; let i = $index) {
            <label class="anim-rise flex items-start gap-3 rounded-xl border p-3 transition-colors"
                   [style.--i]="i" [class.cursor-pointer]="m.ready" [class.opacity-60]="!m.ready"
                   [class]="module === m.id ? 'border-accent bg-accent/5' : 'border-line'">
              <input type="radio" name="module" class="mt-1 accent-accent" [value]="m.id" [(ngModel)]="module" [disabled]="!m.ready">
              <svg width="30" height="30" viewBox="0 0 30 30" fill="none" aria-hidden="true" class="shrink-0">
                <rect x="1" y="1" width="28" height="28" rx="8" class="fill-raised"/>
                <path [attr.d]="m.icon" [attr.class]="m.stroke" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
              </svg>
              <span class="text-sm"><b class="block font-medium">{{ m.name }} @if (!m.ready) { <span class="ml-1 text-xs font-normal text-muted">{{ m.soon }}</span> }</b>
                <span class="text-muted">{{ m.note }}</span></span>
            </label>
          }
        </div>
      </fieldset>
      @if (error()) { <p class="text-sm text-bad">{{ error() }}</p> }
    </form>
    <ng-container footer>
      <button class="btn" (click)="closed.emit()">Cancel</button>
      <button class="btn btn-primary" form="project-form" [disabled]="!name.trim()">Create project</button>
    </ng-container>
  </app-modal>`,
})
export class NewProjectDialog {
  private api = inject(Api);
  private store = inject(WorkspaceStore);
  readonly closed = output<void>();
  readonly created = output<Project>();
  readonly error = signal('');
  name = ''; goal = '';
  module = 'software';
  /** One engine, three modules; Ship and Serve arrive in the next releases. */
  readonly modules = [
    { id: 'software', name: 'Build', ready: true, soon: '', stroke: 'stroke-info',
      note: 'Tickets, pull requests and releases. Forecasts, review times and DORA metrics.', icon: 'M9 10l-3 5 3 5M21 10l3 5-3 5M17 8l-4 14' },
    { id: 'shipments', name: 'Ship', ready: false, soon: 'Coming in v1.5', stroke: 'stroke-accent',
      note: 'Customer orders and deliveries: late-delivery risk by route and carrier.', icon: 'M6 11h12v9H6zM18 14h4l2 3v3h-6M9 23a1.5 1.5 0 1 0 0-3M20 23a1.5 1.5 0 1 0 0-3' },
    { id: 'services', name: 'Serve', ready: false, soon: 'Coming in v1.6', stroke: 'stroke-violet',
      note: 'Service jobs and appointments: missed-visit risk and real job durations.', icon: 'M8 22l7-7M14 9a4 4 0 1 0 5 5l3 3-2 2-3-3a4 4 0 0 1-3-7z' },
  ];

  async save() {
    try {
      const p = await this.api.post<Project>(`/workspaces/${this.store.workspaceId()}/projects`,
        { name: this.name.trim(), goal: this.goal.trim() });
      this.created.emit(p);
    } catch (e) { this.error.set(errorMessage(e)); }
  }
}
