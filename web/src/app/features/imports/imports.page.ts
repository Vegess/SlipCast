import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Api, errorMessage } from '../../core/api.service';
import { WorkspaceStore } from '../../core/workspace.store';
import { ImportReport, ImportReportComponent } from '../../shared/import-report.component';
import { ImportDialog } from '../shell/import.dialog';
import { Project } from '../../core/models';

interface ImportRow {
  id: string; project_id: string | null; project_name: string; filename: string;
  rows_read: number; imported: number; skipped: number; created_at: string; report: ImportReport;
}

@Component({
  selector: 'app-imports',
  imports: [DatePipe, RouterLink, ImportReportComponent, ImportDialog],
  template: `
  <div class="mx-auto max-w-5xl px-4 py-8 sm:px-8">
    <div class="flex flex-wrap items-end gap-3">
      <div class="mr-auto">
        <h1 class="text-3xl font-bold">Imports</h1>
        <p class="note mt-1">Every CSV you have imported, with its data-quality report: what was read, kept, skipped and inferred.</p>
      </div>
      <button class="btn btn-primary" (click)="dialog.set(true)">Import a CSV</button>
    </div>
    @if (error()) { <p class="mt-4 text-sm text-bad">{{ error() }}</p> }

    @if (rows(); as list) {
      @if (!list.length) {
        <section class="card card-info mt-8">
          <h2 class="section-title">No imports yet</h2>
          <p class="note mt-1">Export issues from Jira, GitHub Issues, Trello or Linear as CSV and import them. Columns are mapped automatically.</p>
        </section>
      }
      <ul class="mt-8 grid gap-3">
        @for (r of list; track r.id) {
          <li class="card card-info p-0">
            <button class="flex w-full flex-wrap items-center gap-x-6 gap-y-2 px-5 py-4 text-left" (click)="toggle(r.id)"
                    [attr.aria-expanded]="open() === r.id" [attr.aria-controls]="'report-' + r.id">
              <div class="min-w-0 flex-1">
                <p class="truncate font-medium">{{ r.filename }}</p>
                <p class="text-xs text-muted">{{ r.created_at | date: 'd MMM y, HH:mm' }} · into “{{ r.project_name }}”</p>
              </div>
              <span class="inline-flex items-baseline gap-1.5 text-sm"><b class="font-display text-lg text-ok">{{ r.imported }}</b><span class="text-muted">imported</span></span>
              <span class="inline-flex items-baseline gap-1.5 text-sm"><b class="font-display text-lg" [class.text-bad]="r.skipped">{{ r.skipped }}</b><span class="text-muted">skipped</span></span>
              <span class="text-sm text-muted">{{ r.report.warnings.length }} warning{{ r.report.warnings.length === 1 ? '' : 's' }}</span>
              <span class="text-muted" aria-hidden="true">{{ open() === r.id ? '▴' : '▾' }}</span>
            </button>
            @if (open() === r.id) {
              <div [id]="'report-' + r.id" class="border-t border-line px-5 py-5">
                <app-import-report [report]="r.report" />
                <p class="mt-4 text-sm">
                  @if (r.project_id) { <a class="text-info hover:underline" [routerLink]="['/projects', r.project_id, 'board']">Open “{{ r.project_name }}” →</a> }
                  @else { <span class="text-muted">The project from this import has been deleted; the report is kept for reference.</span> }
                </p>
              </div>
            }
          </li>
        }
      </ul>
    } @else if (!error()) { <p class="note mt-8">Loading imports…</p> }
  </div>
  @if (dialog()) { <app-import-dialog (closed)="closeDialog()" (imported)="imported($event)" /> }`,
})
export class ImportsPage implements OnInit {
  private api = inject(Api);
  private store = inject(WorkspaceStore);
  readonly rows = signal<ImportRow[] | null>(null);
  readonly open = signal<string | null>(null);
  readonly dialog = signal(false);
  readonly error = signal('');

  async ngOnInit() {
    try {
      this.rows.set(await this.api.get<ImportRow[]>(`/workspaces/${this.store.workspaceId()}/imports`));
    } catch (e) { this.error.set(errorMessage(e)); }
  }

  toggle(id: string) { this.open.set(this.open() === id ? null : id); }

  closeDialog() { this.dialog.set(false); this.ngOnInit(); }

  async imported(_: Project) {
    this.dialog.set(false);
    await this.ngOnInit();
    this.open.set(this.rows()?.[0]?.id ?? null);
  }
}
