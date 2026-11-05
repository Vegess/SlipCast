import { Component, OnInit, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { WorkspaceStore } from '../../core/workspace.store';

@Component({
  selector: 'app-welcome',
  template: `
  @if (ready()) {
    <div class="max-w-2xl px-6 py-12 sm:px-10">
      <h1 class="text-4xl font-bold leading-tight">Start with your team's ticket history.</h1>
      <p class="mt-4 text-muted">
        SlipCast works from your real ticket history: when work was created, started, blocked and finished.
        Import a CSV export from Jira, GitHub Issues or Trello, or explore the demo dataset first.
      </p>
      <div class="mt-8 grid gap-4 sm:grid-cols-3">
        <div class="card"><h3 class="section-title">Import history</h3><p class="note mt-1">Columns are mapped automatically from Jira, GitHub or Trello exports.</p></div>
        <div class="card"><h3 class="section-title">Check data quality</h3><p class="note mt-1">See what was imported, skipped and inferred before you trust any number.</p></div>
        <div class="card"><h3 class="section-title">Track every change</h3><p class="note mt-1">Each status move is recorded, building the history that analytics run on.</p></div>
      </div>
      <p class="mt-8 text-sm text-muted">Use <b class="text-fg">Demo data</b> or <b class="text-fg">Import CSV</b> in the sidebar to begin. Past imports and their data-quality reports are listed under <b class="text-fg">Imports</b>.</p>
    </div>
  }`,
})
export class WelcomePage implements OnInit {
  private store = inject(WorkspaceStore);
  private router = inject(Router);
  readonly ready = signal(false);

  async ngOnInit() {
    try { await this.store.load(); } catch { /* shell shows the error */ }
    const first = this.store.projects()[0];
    if (first) this.router.navigate(['/projects', first.id]);
    else this.ready.set(true);
  }
}
