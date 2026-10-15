import { HttpClient } from '@angular/common/http';
import { Component, inject, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { errorMessage } from '../../core/api.service';
import { API_URL } from '../../core/config';
import { Project } from '../../core/models';
import { WorkspaceStore } from '../../core/workspace.store';
import { ModalComponent } from '../../shared/modal.component';

interface ImportReport {
  rows_read: number; imported: number; skipped: number; skipped_reasons: Record<string, number>;
  columns_mapped: Record<string, string>; columns_ignored: string[]; warnings: string[];
  date_range: [string, string] | null; status_counts: Record<string, number>; labelled_types: number;
}

@Component({
  selector: 'app-import-dialog',
  imports: [FormsModule, ModalComponent],
  template: `
  <app-modal heading="Import tickets from CSV" [wide]="!!report()" (closed)="closed.emit()">
    @if (!report()) {
      <div class="grid gap-4">
        <p class="note">Export issues from Jira, GitHub Issues or Trello as CSV. Plotline maps the columns automatically
          and shows a data-quality report. Up to 5,000 rows or 5 MB.</p>
        <label class="label">CSV file
          <input class="input file:mr-3 file:rounded-md file:border-0 file:bg-raised file:px-3 file:py-1 file:text-fg"
                 type="file" accept=".csv,text/csv" (change)="pick($event)">
        </label>
        <label class="label">Project name (optional) <input class="input" [(ngModel)]="name" maxlength="80" placeholder="Defaults to the file name"></label>
        @if (error()) { <p class="text-sm text-bad">{{ error() }}</p> }
      </div>
    } @else {
      @let r = report()!;
      <div class="grid gap-5">
        <div class="grid grid-cols-3 gap-4">
          <div><p class="stat-value">{{ r.rows_read }}</p><p class="note">rows read</p></div>
          <div><p class="stat-value text-ok">{{ r.imported }}</p><p class="note">imported</p></div>
          <div><p class="stat-value" [class.text-bad]="r.skipped">{{ r.skipped }}</p><p class="note">skipped</p></div>
        </div>
        @if (r.skipped) {
          <p class="text-sm">Skipped because:
            @for (e of entries(r.skipped_reasons); track e[0]) { <span class="pill mr-1 bg-bad/15 text-bad">{{ e[0] }}: {{ e[1] }}</span> }
          </p>
        }
        <div>
          <h3 class="section-title mb-2">Columns mapped</h3>
          <table class="table"><tbody>
            @for (e of entries(r.columns_mapped); track e[0]) { <tr><td class="text-muted">{{ fieldLabel[e[0]] ?? e[0] }}</td><td>{{ e[1] }}</td></tr> }
          </tbody></table>
          @if (r.columns_ignored.length) { <p class="note mt-2">Ignored: {{ r.columns_ignored.join(', ') }}</p> }
        </div>
        @if (r.warnings.length) {
          <ul class="list-disc space-y-1 pl-5 text-sm text-accent">@for (w of r.warnings; track w) { <li>{{ w }}</li> }</ul>
        }
        <p class="note">{{ r.labelled_types }} tickets had a type label.
          @if (r.date_range) { Tickets created {{ r.date_range[0] }} to {{ r.date_range[1] }}. }</p>
      </div>
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

  readonly fieldLabel: Record<string, string | undefined> = {
    title: 'Title', description: 'Description', kind: 'Ticket type', status: 'Status', owner: 'Owner',
    priority: 'Priority', created_at: 'Created', started_at: 'Started', completed_at: 'Completed',
    due: 'Due date', external_id: 'Ticket key',
  };

  entries(o: Record<string, unknown>) { return Object.entries(o); }

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
