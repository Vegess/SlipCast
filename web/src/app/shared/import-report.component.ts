import { Component, input } from '@angular/core';

export interface ImportReport {
  rows_read: number; imported: number; skipped: number; skipped_reasons: Record<string, number>;
  columns_mapped: Record<string, string>; columns_ignored: string[]; warnings: string[];
  date_range: [string, string] | null; status_counts: Record<string, number>; labelled_types: number;
}

const FIELD_LABEL: Record<string, string | undefined> = {
  title: 'Title', description: 'Description', kind: 'Ticket type', status: 'Status', owner: 'Owner',
  priority: 'Priority', created_at: 'Created', started_at: 'Started', completed_at: 'Completed',
  due: 'Due date', external_id: 'Ticket key',
};

/** The data-quality report for one CSV import: what was read, kept, skipped and inferred. */
@Component({
  selector: 'app-import-report',
  template: `
  @let r = report();
  <div class="grid gap-5">
    <div class="grid grid-cols-3 gap-4">
      <div><p class="stat-value">{{ r.rows_read }}</p><p class="note">rows read</p></div>
      <div><p class="stat-value text-ok">{{ r.imported }}</p><p class="note">imported</p></div>
      <div><p class="stat-value" [class.text-bad]="r.skipped">{{ r.skipped }}</p><p class="note">skipped</p></div>
    </div>
    @if (r.skipped) {
      <p class="text-sm">Skipped because:
        @for (e of entries(r.skipped_reasons); track e[0]) { <span class="pill mr-1 bg-bad/15 text-bad-strong">{{ e[0] }}: {{ e[1] }}</span> }
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
  </div>`,
})
export class ImportReportComponent {
  readonly report = input.required<ImportReport>();
  readonly fieldLabel = FIELD_LABEL;
  entries(o: Record<string, unknown>) { return Object.entries(o); }
}
