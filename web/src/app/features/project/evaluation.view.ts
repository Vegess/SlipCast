import { Component, computed } from '@angular/core';
import { KIND_LABEL } from '../../core/models';
import { ChartComponent, baseOption } from '../../shared/chart.component';
import { num, pct } from '../../shared/format';
import { projectResource } from './loader';

interface Evaluation {
  classifier: { available: boolean; reason: string; labels: string[]; accuracy: number; macro_f1: number; train_size: number; test_size: number; split: string;
    baseline: { name: string; accuracy: number; macro_f1: number }; per_class: { label: string; precision: number; recall: number; f1: number; support: number }[];
    confusion_matrix: number[][]; top_terms: Record<string, string[]>; predicted_unlabeled: number };
  topics: { available: boolean; silhouette: number; count: number };
  risk: { available: boolean; reason: string; roc_auc: number; average_precision: number; brier: number; base_rate: number; precision_at_50: number; recall_at_50: number;
    train_size: number; test_size: number; split: string; baseline: { name: string; roc_auc: number; average_precision: number };
    roc_curve: [number, number][]; pr_curve: [number, number][]; calibration: [number, number][]; weights: { feature: string; weight: number }[] };
  forecast_backtest: { available: boolean; reason?: string; batch_size: number; p85_hit_rate: number; p50_mean_abs_error_days: number;
    points: { cutoff: string; actual_weeks: number; p50_weeks: number; p85_weeks: number; hit_p85: boolean }[] };
  reference_class: { available: boolean; reason: string; split?: string; train_size?: number; test_size?: number; evaluated?: number;
    coverage_p10_p90?: number; target_coverage?: number; p50_mae_days?: number; baseline?: { name: string; p50_mae_days: number } };
  ledger: { available: boolean; reason: string; total: number; resolved: number; unresolved: number; hit_rate: number | null;
    project: { resolved: number; hit_rate_p85: number | null }; ticket: { resolved: number; hit_rate_p85: number | null; coverage_p10_p90: number | null } };
  advice?: { generated: number; accepted: number; rejected: number; grounding_pass_rate: number | null; feedback: Record<string, { helpful: number; not_helpful: number; helpful_rate: number | null }> };
}

@Component({
  selector: 'app-evaluation-view',
  imports: [ChartComponent],
  template: `
  <p class="note mb-5 max-w-3xl">Every model is tested on data it never saw. Splits are time-based: models train on older tickets and are scored on newer ones,
    the way they're used in practice, so results aren't inflated by peeking at the future. Each model is compared against a simple baseline.</p>
  @if (res.error()) { <p class="text-sm text-bad">{{ res.error() }}</p> }
  @if (res.data(); as e) {
    <!-- classifier -->
    <section class="card">
      <h3 class="section-title">Ticket type classifier <span class="note font-normal">· TF-IDF + logistic regression</span></h3>
      @if (!e.classifier.available) { <p class="note mt-2">{{ e.classifier.reason }}</p> } @else {
        @let c = e.classifier;
        <div class="mt-4 grid gap-6 lg:grid-cols-[1fr_1.1fr]">
          <div>
            <div class="grid grid-cols-2 gap-4">
              <div><p class="stat-value text-ok">{{ pct(c.accuracy) }}</p><p class="note mt-1">accuracy · baseline {{ pct(c.baseline.accuracy) }}</p></div>
              <div><p class="stat-value text-ok">{{ num(c.macro_f1, 2) }}</p><p class="note mt-1">macro F1 · baseline {{ num(c.baseline.macro_f1, 2) }}</p></div>
            </div>
            <p class="note mt-3">Baseline: {{ c.baseline.name }}. Trained on {{ c.train_size }}, tested on {{ c.test_size }} tickets ({{ c.split }}).</p>
            <table class="table mt-4">
              <thead><tr><th>Type</th><th>Precision</th><th>Recall</th><th>F1</th><th>Tickets</th></tr></thead>
              <tbody>@for (r of c.per_class; track r.label) {
                <tr><td>{{ kind(r.label) }}</td><td>{{ num(r.precision, 2) }}</td><td>{{ num(r.recall, 2) }}</td><td>{{ num(r.f1, 2) }}</td><td class="text-muted">{{ r.support }}</td></tr>
              }</tbody>
            </table>
            <h4 class="mt-5 text-sm font-medium">Words that most signal each type</h4>
            <ul class="mt-2 space-y-1 text-sm">@for (l of c.labels; track l) { <li><span class="text-muted">{{ kind(l) }}:</span> {{ (c.top_terms[l] || []).join(', ') }}</li> }</ul>
          </div>
          <div>
            <p class="text-sm font-medium">Confusion matrix</p>
            <p class="note">Rows are the true type, columns the predicted type. A strong diagonal is good.</p>
            <app-chart class="mt-2 h-72" [options]="confusion()" ariaLabel="Confusion matrix" />
          </div>
        </div>
      }
    </section>

    <!-- risk -->
    <section class="card mt-5">
      <h3 class="section-title">Slip-risk model <span class="note font-normal">· logistic regression on ticket, text and workload features</span></h3>
      @if (!e.risk.available) { <p class="note mt-2">{{ e.risk.reason }}</p> } @else {
        @let r = e.risk;
        <div class="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div><p class="stat-value text-ok">{{ num(r.roc_auc, 2) }}</p><p class="note mt-1">ROC-AUC · baseline {{ num(r.baseline.roc_auc, 2) }}</p></div>
          <div><p class="stat-value text-ok">{{ num(r.average_precision, 2) }}</p><p class="note mt-1">avg precision · baseline {{ num(r.baseline.average_precision, 2) }}</p></div>
          <div><p class="stat-value">{{ num(r.brier, 3) }}</p><p class="note mt-1">Brier score (lower is better)</p></div>
          <div><p class="stat-value">{{ pct(r.base_rate) }}</p><p class="note mt-1">of finished tickets were late</p></div>
        </div>
        <p class="note mt-3">Baseline: {{ r.baseline.name }}. At a 50% threshold the model has {{ pct(r.precision_at_50) }} precision and {{ pct(r.recall_at_50) }} recall.
          Trained on {{ r.train_size }}, tested on {{ r.test_size }} finished tickets ({{ r.split }}).</p>
        <div class="mt-4 grid gap-5 lg:grid-cols-3">
          <div><p class="text-sm font-medium">ROC curve</p><app-chart class="mt-2 h-60" [options]="roc()" ariaLabel="ROC curve" /></div>
          <div><p class="text-sm font-medium">Precision–recall</p><app-chart class="mt-2 h-60" [options]="pr()" ariaLabel="Precision recall curve" /></div>
          <div><p class="text-sm font-medium">Calibration</p><p class="note">Do predicted risks match how often tickets were really late?</p><app-chart class="mt-2 h-52" [options]="calibration()" ariaLabel="Calibration chart" /></div>
        </div>
        <h4 class="mt-5 text-sm font-medium">Strongest model weights</h4>
        <p class="note">Positive weights push risk up; numeric features are standardised, so sizes are comparable.</p>
        <ul class="mt-2 grid gap-x-8 gap-y-1 text-sm sm:grid-cols-2">
          @for (w of r.weights; track w.feature) {
            <li class="flex justify-between gap-3"><span class="text-muted">{{ w.feature }}</span><span [class.text-bad]="w.weight > 0" [class.text-ok]="w.weight < 0">{{ w.weight > 0 ? '+' : '' }}{{ w.weight.toFixed(2) }}</span></li>
          }
        </ul>
      }
    </section>

    <!-- backtest -->
    <section class="card mt-5">
      <h3 class="section-title">Forecast backtest <span class="note font-normal">· Monte Carlo replayed at past dates</span></h3>
      @if (!e.forecast_backtest.available) { <p class="note mt-2">{{ e.forecast_backtest.reason }}</p> } @else {
        @let b = e.forecast_backtest;
        <div class="mt-4 grid grid-cols-2 gap-4 sm:max-w-md">
          <div><p class="stat-value" [class.text-ok]="b.p85_hit_rate >= .8" [class.text-accent]="b.p85_hit_rate < .8">{{ pct(b.p85_hit_rate) }}</p><p class="note mt-1">finished within the 85% forecast (target ≈85%)</p></div>
          <div><p class="stat-value">{{ num(b.p50_mean_abs_error_days) }}<span class="text-base text-muted"> d</span></p><p class="note mt-1">average miss of the 50% date</p></div>
        </div>
        <p class="note mt-3">At each past date SlipCast forecast how long the next {{ b.batch_size }} tickets would take, then checked what really happened.</p>
        <app-chart class="mt-3 h-64" [options]="backtest()" ariaLabel="Forecast backtest chart" />
      }
    </section>

    <!-- reference class + ledger -->
    <div class="mt-5 grid gap-5 lg:grid-cols-2">
      <section class="card">
        <h3 class="section-title">Reference-class forecasts <span class="note font-normal">· TF-IDF nearest finished tickets</span></h3>
        @if (!e.reference_class.available) { <p class="note mt-2">{{ e.reference_class.reason }}</p> } @else {
          @let rc = e.reference_class;
          <div class="mt-4 grid grid-cols-2 gap-4">
            <div><p class="stat-value" [class.text-ok]="(rc.coverage_p10_p90 ?? 0) >= .7">{{ pct(rc.coverage_p10_p90) }}</p><p class="note mt-1">of newer tickets finished inside their "similar tickets took X–Y days" range (target ≈80%)</p></div>
            <div><p class="stat-value">{{ num(rc.p50_mae_days) }}<span class="text-base text-muted"> d</span></p><p class="note mt-1">typical miss of the middle estimate · baseline {{ num(rc.baseline?.p50_mae_days) }} d</p></div>
          </div>
          <p class="note mt-3">Baseline: {{ rc.baseline?.name }}. {{ rc.evaluated }} test tickets, {{ rc.split }}.</p>
        }
      </section>
      <section class="card">
        <h3 class="section-title">Forecast ledger <span class="note font-normal">· every forecast, scored when the work finished</span></h3>
        @if (!e.ledger.available) { <p class="note mt-2">{{ e.ledger.reason }}</p> } @else {
          <div class="mt-4 grid grid-cols-3 gap-4">
            <div><p class="stat-value">{{ pct(e.ledger.hit_rate) }}</p><p class="note mt-1">within the 85% estimate ({{ e.ledger.resolved }} scored)</p></div>
            <div><p class="stat-value">{{ pct(e.ledger.ticket.coverage_p10_p90) }}</p><p class="note mt-1">tickets inside their range</p></div>
            <div><p class="stat-value">{{ e.ledger.unresolved }}</p><p class="note mt-1">still pending</p></div>
          </div>
          <p class="note mt-3">Unlike the backtests above, these are the forecasts users actually saw, scored against what happened next.</p>
        }
      </section>
    </div>

    <!-- topics + advice -->
    <div class="mt-5 grid gap-5 lg:grid-cols-2">
      <section class="card">
        <h3 class="section-title">Theme clustering</h3>
        @if (e.topics.available) {
          <p class="mt-3"><span class="stat-value">{{ num(e.topics.silhouette, 2) }}</span></p>
          <p class="note mt-1">Cosine silhouette score for {{ e.topics.count }} themes; k was chosen automatically by maximising it. Short ticket text usually scores 0.1–0.3, so treat themes as a guide, not ground truth.</p>
        } @else { <p class="note mt-2">Not enough text to cluster yet.</p> }
      </section>
      @if (e.advice; as adv) {
      <section class="card">
        <h3 class="section-title">AI advice quality</h3>
        <div class="mt-3 grid grid-cols-2 gap-4">
          <div><p class="stat-value">{{ adv.grounding_pass_rate === null ? '—' : pct(adv.grounding_pass_rate) }}</p><p class="note mt-1">AI suggestions that passed the grounding check ({{ adv.accepted }}/{{ adv.generated }})</p></div>
          <div><p class="stat-value">{{ helpful('llm') }}</p><p class="note mt-1">rated helpful (AI) · rules: {{ helpful('rules') }}</p></div>
        </div>
        <p class="note mt-3">The grounding check rejects any suggestion that cites no finding or uses a number that isn't in the findings.</p>
      </section>
      }
    </div>
  } @else if (!res.error()) { <p class="note">Evaluating models…</p> }`,
})
export class EvaluationView {
  readonly res = projectResource<Evaluation>((id) => `/projects/${id}/analytics/evaluation`);
  readonly num = num; readonly pct = pct;
  kind(k: string) { return KIND_LABEL[k] ?? k; }
  helpful(src: string) {
    const f = this.res.data()?.advice?.feedback[src];
    return f?.helpful_rate === null || f === undefined ? '—' : pct(f.helpful_rate);
  }

  private axes(xName: string, yName: string, max = 1) {
    const ax = (name: string) => ({ type: 'value', name, min: 0, max, nameLocation: 'middle', nameGap: 26, axisLabel: { color: '#8E98AE', fontSize: 10 },
      splitLine: { lineStyle: { color: '#1F2638' } }, axisLine: { lineStyle: { color: '#262E42' } }, nameTextStyle: { color: '#8E98AE', fontSize: 11 } });
    return { xAxis: ax(xName), yAxis: { ...ax(yName), nameGap: 30 }, grid: { left: 44, right: 12, top: 12, bottom: 40 } };
  }

  readonly confusion = computed(() => {
    const c = this.res.data()?.classifier;
    if (!c?.available) return {};
    const labels = c.labels.map((l) => this.kind(l));
    const data: [number, number, number][] = [];
    c.confusion_matrix.forEach((row, i) => row.forEach((v, j) => data.push([j, labels.length - 1 - i, v])));
    const max = Math.max(...data.map((d) => d[2]), 1);
    return baseOption({
      grid: { left: 80, right: 12, top: 8, bottom: 40 },
      tooltip: { trigger: 'item', backgroundColor: '#1B2235', borderColor: '#262E42', textStyle: { color: '#E5E9F2' },
        formatter: (p: { data: [number, number, number] }) => `True ${labels[labels.length - 1 - p.data[1]]}, predicted ${labels[p.data[0]]}: ${p.data[2]}` },
      xAxis: { type: 'category', data: labels, name: 'predicted', nameLocation: 'middle', nameGap: 26, axisLabel: { color: '#8E98AE' }, nameTextStyle: { color: '#8E98AE' }, axisLine: { lineStyle: { color: '#262E42' } } },
      yAxis: { type: 'category', data: [...labels].reverse(), axisLabel: { color: '#8E98AE' }, axisLine: { lineStyle: { color: '#262E42' } } },
      visualMap: { show: false, min: 0, max, inRange: { color: ['#141A29', '#7D96F2'] } },
      series: [{ type: 'heatmap', data, label: { show: true, color: '#E5E9F2' }, itemStyle: { borderColor: '#0D1220', borderWidth: 2 } }],
    });
  });

  readonly roc = computed(() => {
    const r = this.res.data()?.risk;
    if (!r?.available) return {};
    return baseOption({ ...this.axes('false positive rate', 'true positive rate'), tooltip: { show: false },
      series: [
        { type: 'line', symbol: 'none', data: r.roc_curve, lineStyle: { color: '#52B5AA', width: 2.5 }, areaStyle: { color: '#52B5AA', opacity: 0.1 } },
        { type: 'line', symbol: 'none', data: [[0, 0], [1, 1]], lineStyle: { color: '#8E98AE', type: 'dashed' } },
      ] });
  });

  readonly pr = computed(() => {
    const r = this.res.data()?.risk;
    if (!r?.available) return {};
    return baseOption({ ...this.axes('recall', 'precision'), tooltip: { show: false },
      series: [
        { type: 'line', symbol: 'none', data: r.pr_curve, lineStyle: { color: '#7D96F2', width: 2.5 } },
        { type: 'line', symbol: 'none', data: [[0, r.base_rate], [1, r.base_rate]], lineStyle: { color: '#8E98AE', type: 'dashed' } },
      ] });
  });

  readonly calibration = computed(() => {
    const r = this.res.data()?.risk;
    if (!r?.available) return {};
    return baseOption({ ...this.axes('predicted risk', 'observed late rate'), tooltip: { show: false },
      series: [
        { type: 'line', symbol: 'circle', symbolSize: 7, data: r.calibration, lineStyle: { color: '#F2B632', width: 2 }, itemStyle: { color: '#F2B632' } },
        { type: 'line', symbol: 'none', data: [[0, 0], [1, 1]], lineStyle: { color: '#8E98AE', type: 'dashed' } },
      ] });
  });

  readonly backtest = computed(() => {
    const b = this.res.data()?.forecast_backtest;
    if (!b?.available) return {};
    const x = b.points.map((p) => p.cutoff.slice(5));
    return baseOption({
      xAxis: { type: 'category', data: x, axisLabel: { color: '#8E98AE' }, axisLine: { lineStyle: { color: '#262E42' } } },
      yAxis: { type: 'value', name: 'weeks', axisLabel: { color: '#8E98AE' }, splitLine: { lineStyle: { color: '#1F2638' } }, nameTextStyle: { color: '#8E98AE' } },
      series: [
        { name: '85% forecast', type: 'line', symbol: 'none', data: b.points.map((p) => p.p85_weeks), lineStyle: { color: '#F2B632', type: 'dashed' }, itemStyle: { color: '#F2B632' } },
        { name: '50% forecast', type: 'line', symbol: 'none', data: b.points.map((p) => p.p50_weeks), lineStyle: { color: '#7D96F2', type: 'dashed' }, itemStyle: { color: '#7D96F2' } },
        { name: 'Actual', type: 'line', symbolSize: 7, data: b.points.map((p) => ({ value: p.actual_weeks, itemStyle: { color: p.hit_p85 ? '#52B5AA' : '#E66C63' } })), lineStyle: { color: '#E5E9F2' } },
      ],
    });
  });
}
