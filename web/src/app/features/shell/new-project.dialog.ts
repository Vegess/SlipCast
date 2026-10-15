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

  async save() {
    try {
      const p = await this.api.post<Project>(`/workspaces/${this.store.workspaceId()}/projects`,
        { name: this.name.trim(), goal: this.goal.trim() });
      this.created.emit(p);
    } catch (e) { this.error.set(errorMessage(e)); }
  }
}
