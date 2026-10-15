import { NgClass } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { Api, errorMessage } from '../../core/api.service';
import { Finding, Suggestion } from '../../core/models';
import { WorkspaceStore } from '../../core/workspace.store';
import { MarkdownComponent } from '../../shared/markdown.component';
import { ProjectContext } from './project.context';

interface Advice {
  provider: string; suggestions: Suggestion[]; findings: Finding[]; privacy_mode: boolean; error: string | null;
  validation: { generated: number; accepted: number; rejected: number; problems: string[] } | null;
  feedback: Record<string, boolean>;
}

@Component({
  selector: 'app-advice-view',
  imports: [MarkdownComponent, NgClass],
  template: `
  <div class="grid gap-5 xl:grid-cols-[1.35fr_1fr]">
    <section>
      <div class="flex flex-wrap items-center gap-3">
        <div class="mr-auto">
          <h3 class="section-title">What to do this week</h3>
          <p class="note">Suggestions are written only from the findings on the right. Each one cites the findings it addresses.</p>
        </div>
        <button class="btn btn-primary" (click)="run()" [disabled]="busy()">{{ busy() ? 'Thinking…' : advice() ? 'Refresh advice' : 'Get advice' }}</button>
      </div>
      @if (store.privacyMode()) { <p class="mt-3 rounded-lg bg-raised px-3 py-2 text-xs text-muted">Privacy mode is on: ticket titles and theme names are removed before anything is sent to the AI.</p> }
      @if (error()) { <p class="mt-3 text-sm text-bad">{{ error() }}</p> }

      @if (advice(); as a) {
        @if (a.validation) {
          <p class="mt-4 text-xs text-muted">
            {{ a.validation.accepted }} of {{ a.validation.generated }} AI suggestions passed the grounding check.
            @if (a.validation.rejected) { Rejected: {{ a.validation.problems.join('; ') }}. }
          </p>
        }
        @if (a.error) { <p class="mt-2 text-xs text-accent">{{ a.error }} Showing rule-based suggestions instead.</p> }
        <ul class="mt-4 space-y-3">
          @for (s of a.suggestions; track s.key) {
            <li class="card p-4">
              <div class="flex flex-wrap items-center gap-2">
                <span class="pill" [ngClass]="impactClass[s.impact]">{{ s.impact }} impact</span>
                <span class="pill bg-raised text-muted">{{ s.source === 'llm' ? 'AI · validated' : 'Rule-based' }}</span>
              </div>
              <p class="mt-2 font-medium">{{ s.title }}</p>
              <p class="mt-1 text-sm text-fg/85">{{ s.action }}</p>
              <p class="mt-2 text-xs text-muted">Based on: @for (id of s.finding_ids; track id) { <span class="mr-2">{{ id }} — {{ findingText(id) }}</span> }</p>
              <div class="mt-3 flex items-center gap-2 text-xs text-muted">
                Was this useful?
                <button class="btn px-2 py-1 text-xs" [class.!border-ok]="vote(s.key) === true" (click)="rate(s, true)">Yes</button>
                <button class="btn px-2 py-1 text-xs" [class.!border-bad]="vote(s.key) === false" (click)="rate(s, false)">No</button>
              </div>
            </li>
          } @empty { <li class="note">No findings to act on. The project looks healthy.</li> }
        </ul>
      }

      <section class="card mt-6">
        <div class="flex flex-wrap items-center gap-3">
          <h3 class="section-title mr-auto">Weekly status report</h3>
          @if (report()) { <button class="btn btn-ghost" (click)="copy()">{{ copied() ? 'Copied' : 'Copy' }}</button> }
          <button class="btn" (click)="writeReport()" [disabled]="reportBusy()">{{ reportBusy() ? 'Writing…' : report() ? 'Rewrite' : 'Write report' }}</button>
        </div>
        @if (report(); as r) { <div class="mt-4"><app-markdown [source]="r.report" /></div>
          <p class="mt-3 text-xs text-muted">Written by {{ r.provider === 'groq' ? 'the AI from computed findings' : 'the built-in template' }}.</p> }
        @else { <p class="note mt-2">Summary, delivery numbers, risks and next week's focus, ready to paste into Slack or email.</p> }
      </section>
    </section>

    <aside class="card h-fit">
      <h3 class="section-title">Findings</h3>
      <p class="note">Computed by statistics and models, not by the AI.</p>
      @if (advice(); as a) {
        <ol class="mt-3 space-y-3 text-sm">
          @for (f of a.findings; track f.id) {
            <li class="flex gap-2.5">
              <span class="mt-0.5 w-7 shrink-0 text-xs font-semibold" [class.text-bad]="f.severity === 'critical'" [class.text-accent]="f.severity === 'warning'" [class.text-info]="f.severity === 'info'">{{ f.id }}</span>
              <span>{{ f.text }}</span>
            </li>
          }
        </ol>
      } @else { <p class="note mt-3">Click "Get advice" to compute findings.</p> }
    </aside>
  </div>`,
})
export class AdviceView {
  private api = inject(Api);
  private ctx = inject(ProjectContext);
  readonly store = inject(WorkspaceStore);
  readonly impactClass = { high: 'bg-bad/15 text-bad', medium: 'bg-accent/15 text-accent', low: 'bg-raised text-muted' };
  readonly advice = signal<Advice | null>(null);
  readonly busy = signal(false);
  readonly error = signal('');
  readonly votes = signal<Record<string, boolean>>({});
  readonly report = signal<{ report: string; provider: string } | null>(null);
  readonly reportBusy = signal(false);
  readonly copied = signal(false);
  private findingMap = computed(() => Object.fromEntries((this.advice()?.findings ?? []).map((f) => [f.id, f.text])));

  findingText(id: string) {
    const t = this.findingMap()[id] ?? '';
    return t.length > 90 ? t.slice(0, 87) + '…' : t;
  }
  vote(key: string) { return this.votes()[key]; }

  async run() {
    this.busy.set(true);
    this.error.set('');
    try {
      const a = await this.api.post<Advice>(`/projects/${this.ctx.id()}/advice`, { privacy_mode: this.store.privacyMode() });
      this.advice.set(a);
      this.votes.set(a.feedback);
    } catch (e) { this.error.set(errorMessage(e)); }
    finally { this.busy.set(false); }
  }

  async rate(s: Suggestion, helpful: boolean) {
    this.votes.update((v) => ({ ...v, [s.key]: helpful }));
    try { await this.api.post(`/projects/${this.ctx.id()}/feedback`, { suggestion_key: s.key, source: s.source, helpful }); }
    catch (e) { this.error.set(errorMessage(e)); }
  }

  async writeReport() {
    this.reportBusy.set(true);
    try { this.report.set(await this.api.post(`/projects/${this.ctx.id()}/status-report`, { privacy_mode: this.store.privacyMode() })); }
    catch (e) { this.error.set(errorMessage(e)); }
    finally { this.reportBusy.set(false); }
  }

  async copy() {
    try { await navigator.clipboard.writeText(this.report()!.report); this.copied.set(true); setTimeout(() => this.copied.set(false), 1500); }
    catch { /* clipboard blocked */ }
  }
}
