import { HttpClient } from '@angular/common/http';
import { Component, inject, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { errorMessage } from '../../core/api.service';
import { API_URL } from '../../core/config';
import { Project } from '../../core/models';
import { WorkspaceStore } from '../../core/workspace.store';
import { ImportReport, ImportReportComponent } from '../../shared/import-report.component';
import { ModalComponent } from '../../shared/modal.component';

@Component({
  selector: 'app-import-dialog',
  imports: [FormsModule, ModalComponent, ImportReportComponent],
  template: `
  <app-modal heading="Import tickets from CSV" [wide]="!!report()" (closed)="closed.emit()">
    @if (!report()) {
      <div class="grid gap-4">
        <p class="note">Export issues from Jira, GitHub Issues or Trello as CSV. SlipCast maps the columns automatically
          and shows a data-quality report. Up to 5,000 rows or 5 MB.</p>
        <label class="label">CSV file
          <input class="input file:mr-3 file:rounded-md file:border-0 file:bg-raised file:px-3 file:py-1 file:text-fg"
                 type="file" accept=".csv,text/csv" (change)="pick($event)">
        </label>
        <label class="label">Project name (optional) <input class="input" [(ngModel)]="name" maxlength="80" placeholder="Defaults to the file name"></label>
        @if (error()) { <p class="text-sm text-bad">{{ error() }}</p> }
      </div>
    } @else {
      <app-import-report [report]="report()!" />
    }
    <ng-container footer>
      @if (!report()) {
        <button class="btn" (click)="closed.emit()">Cancel</button>
        <button class="btn btn-primary" [disabled]="!file || busy()" (click)="upload()">{{ busy() ? 'Importing…' : 'Import' }}</button>
      } @else {
        <button class="btn btn-primary" (click)="imported.emit(project!)">Open project</button>
      }
    </ng-container>
  </app-modal>`,
})
export class ImportDialog {
  private http = inject(HttpClient);
  private store = inject(WorkspaceStore);
  readonly closed = output<void>();
  readonly imported = output<Project>();
  readonly busy = signal(false);
  readonly error = signal('');
  readonly report = signal<ImportReport | null>(null);
  file: File | null = null;
  name = '';
  project: Project | null = null;

  pick(ev: Event) { this.file = (ev.target as HTMLInputElement).files?.[0] ?? null; }

  async upload() {
    if (!this.file) return;
    this.busy.set(true);
    this.error.set('');
    const form = new FormData();
    form.append('file', this.file);
    form.append('project_name', this.name.trim());
    try {
      const res = await firstValueFrom(this.http.post<{ project: Project; report: ImportReport }>(
        `${API_URL}/workspaces/${this.store.workspaceId()}/import`, form));
      this.project = res.project;
      this.report.set(res.report);
      this.store.load();
    } catch (e) {
      this.error.set(errorMessage(e));
    } finally {
      this.busy.set(false);
    }
  }
}
