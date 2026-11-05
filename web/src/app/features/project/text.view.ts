import { Component, computed } from '@angular/core';
import { KIND_LABEL } from '../../core/models';
import { ChartComponent, baseOption } from '../../shared/chart.component';
import { num } from '../../shared/format';
import { projectResource } from './loader';

interface TextInsights {
  topics: { available: boolean; reason: string; silhouette: number;
    items: { name: string; size: number; keywords: string[]; open: number; median_cycle_days: number | null; kinds: Record<string, number> }[] };
  duplicates: { similarity: number; a: { id: string; title: string; status: string }; b: { id: string; title: string; status: string } }[];
  quality: { average_open: number | null; lowest: { id: string; title: string; score: number; reasons: string[] }[] };
  types: { counts: Record<string, number>; predicted: number; classifier_available: boolean };
}

@Component({
  selector: 'app-text-view',
  imports: [ChartComponent],
  template: `
  @if (res.error()) { <p class="text-sm text-bad">{{ res.error() }}</p> }
  @if (res.data(); as d) {
    <div class="grid gap-5 xl:grid-cols-[1.4fr_1fr]">
      <section class="card">
        <h3 class="section-title">Themes found in ticket text</h3>
        <p class="note">K-means clustering on TF-IDF vectors groups tickets by what they talk about, with no manual tagging. Names are each cluster's strongest words.</p>
        @if (!d.topics.available) { <p class="note mt-3">{{ d.topics.reason }}</p> } @else {
          <app-chart class="mt-3 h-64" [options]="topicChart()" ariaLabel="Median cycle time by theme" />
          <div class="mt-4 grid gap-3 sm:grid-cols-2">
            @for (t of d.topics.items; track t.name) {
              <div class="rounded-lg border border-line p-3">
                <p class="font-medium">{{ t.name }}</p>
                <p class="mt-1 text-xs text-muted">{{ t.size }} tickets · {{ t.open }} open · median {{ num(t.median_cycle_days) }} days</p>
                <p class="mt-2 flex flex-wrap gap-1">@for (k of t.keywords.slice(0, 6); track k) { <span class="pill bg-raised text-muted">{{ k }}</span> }</p>
              </div>
            }
          </div>
        }
      </section>

      <div class="grid content-start gap-5">
        <section class="card">
          <h3 class="section-title">Ticket types</h3>
          <p class="note">
            @if (d.types.classifier_available) { {{ d.types.predicted }} unlabelled tickets were typed by the text classifier. }
            @else { Not enough labelled tickets to train the type classifier yet. }
          </p>
          <ul class="mt-3 space-y-2 text-sm">
            @for (k of typeRows(); track k.key) {
              <li class="grid grid-cols-[90px_1fr_36px] items-center gap-3">
                <span>{{ k.label }}</span>
                <span class="h-2 overflow-hidden rounded-full bg-raised"><span class="block h-full rounded-full bg-info" [style.width.%]="k.share"></span></span>
                <span class="text-right text-muted">{{ k.count }}</span>
              </li>
            }
          </ul>
        </section>
        <section class="card">
          <h3 class="section-title">Weakest open tickets</h3>
          <p class="note">Average open-ticket quality: <b class="text-fg">{{ num(d.quality.average_open, 0) }}/100</b>. Vague tickets take longer and slip more often.</p>
          <ul class="mt-3 divide-y divide-line/60">
            @for (q of d.quality.lowest.slice(0, 6); track q.id) {
              <li class="py-2 text-sm">
                <div class="flex gap-3"><span class="w-10 shrink-0 font-display text-lg" [class.text-bad]="q.score < 60">{{ q.score }}</span><span class="font-medium">{{ q.title }}</span></div>
                <p class="ml-[52px] text-xs text-muted">{{ q.reasons.join(' · ') }}</p>
              </li>
            }
          </ul>
        </section>
      </div>
    </div>

    <section class="card mt-5">
      <h3 class="section-title">Likely duplicates</h3>
      <p class="note">Pairs whose text is at least 72% similar (cosine similarity of TF-IDF vectors). Open tickets are listed first.</p>
      @if (!d.duplicates.length) { <p class="note mt-3">No likely duplicates found.</p> } @else {
        <div class="mt-3 overflow-x-auto">
          <table class="table">
            <thead><tr><th>Similarity</th><th>Ticket</th><th>Looks like</th></tr></thead>
            <tbody>
              @for (p of d.duplicates.slice(0, 12); track $index) {
                <tr>
                  <td class="font-display text-base">{{ (p.similarity * 100).toFixed(0) }}%</td>
                  <td>{{ p.a.title }} <span class="text-xs text-muted">({{ p.a.status }})</span></td>
                  <td>{{ p.b.title }} <span class="text-xs text-muted">({{ p.b.status }})</span></td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }
    </section>
  } @else if (!res.error()) { <p class="note">Reading tickets…</p> }`,
})
export class TextView {
  readonly res = projectResource<TextInsights>((id) => `/projects/${id}/analytics/text`);
  readonly num = num;

  readonly typeRows = computed(() => {
    const c = this.res.data()?.types.counts ?? {};
    const total = Object.values(c).reduce((a, b) => a + b, 0) || 1;
    return Object.entries(c).sort((a, b) => b[1] - a[1]).map(([key, count]) => ({ key, count, label: KIND_LABEL[key] ?? key, share: (count / total) * 100 }));
  });

  readonly topicChart = computed(() => {
    const items = [...(this.res.data()?.topics.items ?? [])].filter((t) => t.median_cycle_days !== null)
      .sort((a, b) => (a.median_cycle_days ?? 0) - (b.median_cycle_days ?? 0));
    return baseOption({
      grid: { left: 150, right: 24, top: 8, bottom: 40 },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, backgroundColor: '#1B2235', borderColor: '#262E42', textStyle: { color: '#E5E9F2' } },
      xAxis: { type: 'value', name: 'median cycle time (days)', nameLocation: 'middle', nameGap: 24, axisLabel: { color: '#8E98AE' }, splitLine: { lineStyle: { color: '#1F2638' } }, nameTextStyle: { color: '#8E98AE' } },
      yAxis: { type: 'category', data: items.map((t) => t.name), axisLabel: { color: '#E5E9F2', fontSize: 11 }, axisLine: { lineStyle: { color: '#262E42' } } },
      series: [{ type: 'bar', data: items.map((t) => t.median_cycle_days), itemStyle: { color: '#7D96F2', borderRadius: [0, 3, 3, 0] }, barMaxWidth: 18 }],
    });
  });
}
