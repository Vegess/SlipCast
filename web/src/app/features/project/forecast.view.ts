import { Component, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ChartComponent, baseOption } from '../../shared/chart.component';
import { longDate, pct, shortDate, todayISO } from '../../shared/format';
import { projectResource } from './loader';

interface Ledger {
  available: boolean; reason: string; total: number; resolved: number; unresolved: number; void: number; hit_rate: number | null;
  project: { resolved: number; hit_rate_p85: number | null };
  ticket: { resolved: number; hit_rate_p85: number | null; coverage_p10_p90: number | null };
  calibration: { kind: string; predicted: number; observed: number; n: number }[];
  entries: { id: string; kind: string; made_at: string; subject: string; p50: string | number | null; p85: string | number | null;
    band?: [number, number]; actual: string | number | null; resolved: boolean; void: boolean; hit_p85: boolean | null }[];
}
interface Forecast {
  forecast: {
    available: boolean; reason?: string; remaining: number; p50: string; p85: string; p95: string;
    weeks_p50: number; weeks_p85: number; history_weeks: number[]; simulations: number;
    histogram: { week: number; probability: number }[]; target?: string; target_probability?: number;
  };
  burnup: { dates: string[]; scope: number[]; done: number[]; projection?: { p50: [string, number][]; p85: [string, number][] } };
}

@Component({
  selector: 'app-forecast-view',
  imports: [ChartComponent, FormsModule],
  template: `
  @if (fc.error()) { <p class="text-sm text-bad">{{ fc.error() }}</p> }
  @if (fc.data(); as d) {
    @if (!d.forecast.available) { <p class="note">{{ d.forecast.reason }}</p> } @else {
      @let f = d.forecast;
      <div class="grid gap-5 xl:grid-cols-[1fr_1.4fr]">
        <section>
          <p class="note">When will the {{ f.remaining }} open tickets be done?</p>
          <div class="mt-4 grid grid-cols-3 gap-4">
            <div><p class="stat-value">{{ longDate(f.p50) }}</p><p class="note mt-1">50% likely</p></div>
            <div><p class="stat-value text-accent">{{ longDate(f.p85) }}</p><p class="note mt-1">85% likely</p></div>
            <div><p class="stat-value">{{ longDate(f.p95) }}</p><p class="note mt-1">95% likely</p></div>
          </div>
          <p class="note mt-5">
            SlipCast ran {{ f.simulations.toLocaleString() }} simulations, each replaying random weeks from your last
            12 weeks of throughput ({{ f.history_weeks.join(', ') }} tickets) until the remaining work is done.
            Committing to the 85% date means you'd hit it in 17 of 20 similar situations.
          </p>
          <div class="card mt-5">
            <label class="label">Check a target date
              <input class="input max-w-[200px]" type="date" [min]="today" [ngModel]="target()" (ngModelChange)="target.set($event)">
            </label>
            @if (f.target_probability !== undefined) {
              <p class="mt-3 text-sm"><span class="font-display text-2xl" [class.text-ok]="f.target_probability >= .85" [class.text-accent]="f.target_probability >= .5 && f.target_probability < .85" [class.text-bad]="f.target_probability < .5">{{ pct(f.target_probability) }}</span>
                chance of finishing by {{ longDate(f.target!) }}, assuming no new tickets are added.</p>
            }
          </div>
        </section>
        <section class="card">
          <h3 class="section-title">Distribution of outcomes</h3>
          <p class="note">How many weeks the simulations needed.</p>
          <app-chart class="mt-3 h-64" [options]="histogram()" ariaLabel="Forecast histogram" />
        </section>
      </div>
      <section class="card mt-5">
        <h3 class="section-title">Burn-up</h3>
        <p class="note">Total scope versus finished work. Dashed lines project today's pace to the 50% and 85% dates; a rising scope line pushes both out.</p>
        <app-chart class="mt-3 h-72" [options]="burnup()" ariaLabel="Burn-up chart" />
      </section>
    }
  }

  <section class="card mt-5">
    <h3 class="section-title">Track record</h3>
    <p class="note">Every forecast SlipCast makes is stored and scored automatically when the work is done, so you can see how often it has really been right for this team.</p>
    @if (ledger.data(); as l) {
      @if (!l.available) { <p class="note mt-3">{{ l.reason }}</p> } @else {
        <div class="mt-4 grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-4">
          <div><p class="stat-value" [class.text-ok]="(l.hit_rate ?? 0) >= .75" [class.text-accent]="(l.hit_rate ?? 0) < .75">{{ pct(l.hit_rate) }}</p><p class="note mt-1">of {{ l.resolved }} scored forecasts landed within their 85% estimate</p></div>
          <div><p class="stat-value">{{ pct(l.project.hit_rate_p85) }}</p><p class="note mt-1">completion forecasts on time ({{ l.project.resolved }})</p></div>
          <div><p class="stat-value">{{ pct(l.ticket.coverage_p10_p90) }}</p><p class="note mt-1">tickets inside their "took X–Y days" range (aim ≈80%)</p></div>
          <div><p class="stat-value">{{ l.unresolved }}</p><p class="note mt-1">forecasts still waiting for an outcome</p></div>
        </div>
        <div class="mt-5 grid gap-5 lg:grid-cols-[1fr_1.3fr]">
          <div>
            <p class="text-sm font-medium">Calibration</p>
            <p class="note">If SlipCast says "85% likely", about 85% of those should come true. Points on the dashed line mean the stated odds can be trusted.</p>
            <app-chart class="mt-2 h-64" [options]="calibration()" ariaLabel="Forecast calibration chart" />
          </div>
          <div class="overflow-x-auto">
            <p class="text-sm font-medium">Latest forecasts</p>
            <table class="table mt-2">
              <thead><tr><th>Made</th><th>Forecast for</th><th>85% estimate</th><th>Actual</th><th>Result</th></tr></thead>
              <tbody>
                @for (e of l.entries.slice(0, 12); track e.id) {
                  <tr>
                    <td class="whitespace-nowrap text-muted">{{ shortDate(e.made_at) }}</td>
                    <td class="max-w-[220px] truncate" [title]="e.subject">{{ e.subject }}</td>
                    <td class="whitespace-nowrap">{{ show(e.p85, e.kind) }}</td>
                    <td class="whitespace-nowrap">{{ e.actual === null ? '—' : show(e.actual, e.kind) }}</td>
                    <td>
                      @if (e.void) { <span class="pill bg-raised text-muted">Void</span> }
                      @else if (!e.resolved) { <span class="pill bg-raised text-muted">Pending</span> }
                      @else if (e.hit_p85) { <span class="pill bg-ok/15 text-ok">Hit</span> }
                      @else { <span class="pill bg-bad/15 text-bad">Miss</span> }
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        </div>
      }
    }
  </section>`,
})
export class ForecastView {
  readonly target = signal<string>('');
  readonly fc = projectResource<Forecast>((id) => `/projects/${id}/analytics/forecast`, (): Record<string, string> => (this.target() ? { target: this.target() } : {}));
  readonly ledger = projectResource<Ledger>((id) => `/projects/${id}/forecast-ledger`);
  readonly longDate = longDate; readonly pct = pct; readonly shortDate = shortDate; readonly today = todayISO();

  show(v: string | number | null, kind: string) {
    if (v === null) return '—';
    return kind === 'project_completion' ? longDate(String(v)) : `${Number(v).toFixed(1)} days`;
  }

  readonly calibration = computed(() => {
    const l = this.ledger.data();
    if (!l?.available) return {};
    const series = (kind: string, name: string, color: string) => ({
      name, type: 'line', symbolSize: 9, data: l.calibration.filter((c) => c.kind === kind).map((c) => [c.predicted, c.observed]),
      lineStyle: { color, width: 2 }, itemStyle: { color },
    });
    const ax = (name: string) => ({ type: 'value', name, min: 0, max: 1, nameLocation: 'middle', nameGap: 26,
      axisLabel: { color: '#8E98AE', formatter: (v: number) => `${Math.round(v * 100)}%` }, splitLine: { lineStyle: { color: '#1F2638' } },
      axisLine: { lineStyle: { color: '#262E42' } }, nameTextStyle: { color: '#8E98AE' } });
    return baseOption({
      grid: { left: 48, right: 12, top: 30, bottom: 40 },
      legend: { top: 0, textStyle: { color: '#8E98AE' } },
      tooltip: { trigger: 'item', backgroundColor: '#1B2235', borderColor: '#262E42', textStyle: { color: '#E5E9F2' },
        formatter: (p: { seriesName: string; data: [number, number] }) => `${p.seriesName}: said ${Math.round(p.data[0] * 100)}%, happened ${Math.round(p.data[1] * 100)}%` },
      xAxis: ax('stated probability'), yAxis: { ...ax('how often it came true'), nameGap: 36 },
      series: [
        series('ticket_reference_class', 'Ticket durations', '#7D96F2'),
        series('project_completion', 'Completion dates', '#F2B632'),
        { type: 'line', symbol: 'none', silent: true, data: [[0, 0], [1, 1]], lineStyle: { color: '#8E98AE', type: 'dashed' } },
      ],
    });
  });

  readonly histogram = computed(() => {
    const f = this.fc.data()?.forecast;
    if (!f?.available) return {};
    const p85 = Math.ceil(f.weeks_p85);
    return baseOption({
      xAxis: { type: 'category', name: 'weeks', data: f.histogram.map((h) => h.week + 1), axisLabel: { color: '#8E98AE' }, axisLine: { lineStyle: { color: '#262E42' } }, nameTextStyle: { color: '#8E98AE' } },
      yAxis: { type: 'value', axisLabel: { color: '#8E98AE', formatter: (v: number) => `${Math.round(v * 100)}%` }, splitLine: { lineStyle: { color: '#1F2638' } } },
      tooltip: { trigger: 'axis', backgroundColor: '#1B2235', borderColor: '#262E42', textStyle: { color: '#E5E9F2' }, valueFormatter: (v: number) => `${(v * 100).toFixed(1)}%` },
      series: [{ type: 'bar', data: f.histogram.map((h) => ({ value: h.probability, itemStyle: { color: h.week + 1 <= p85 ? '#F2B632' : '#3A4258', borderRadius: [3, 3, 0, 0] } })) }],
    });
  });

  readonly burnup = computed(() => {
    const b = this.fc.data()?.burnup;
    if (!b) return {};
    const series: Record<string, unknown>[] = [
      { name: 'Scope', type: 'line', symbol: 'none', data: b.dates.map((d, i) => [d, b.scope[i]]), lineStyle: { color: '#8E98AE' }, itemStyle: { color: '#8E98AE' } },
      { name: 'Done', type: 'line', symbol: 'none', data: b.dates.map((d, i) => [d, b.done[i]]), lineStyle: { color: '#52B5AA', width: 2.5 }, itemStyle: { color: '#52B5AA' }, areaStyle: { color: '#52B5AA', opacity: 0.12 } },
    ];
    if (b.projection) {
      series.push({ name: '50% pace', type: 'line', symbol: 'circle', data: b.projection.p50, lineStyle: { type: 'dashed', color: '#7D96F2' }, itemStyle: { color: '#7D96F2' } });
      series.push({ name: '85% pace', type: 'line', symbol: 'circle', data: b.projection.p85, lineStyle: { type: 'dashed', color: '#F2B632' }, itemStyle: { color: '#F2B632' } });
    }
    return baseOption({
      xAxis: { type: 'time', axisLabel: { color: '#8E98AE' }, axisLine: { lineStyle: { color: '#262E42' } }, splitLine: { show: false } },
      yAxis: { type: 'value', axisLabel: { color: '#8E98AE' }, splitLine: { lineStyle: { color: '#1F2638' } } },
      series,
    });
  });
}
