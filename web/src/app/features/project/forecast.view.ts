import { Component, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ChartComponent, baseOption } from '../../shared/chart.component';
import { longDate, pct, todayISO } from '../../shared/format';
import { projectResource } from './loader';

interface Forecast {
  forecast: {
    available: boolean; reason?: string; remaining: number; p50: string; p85: string; p95: string;
    weeks_p50: number; weeks_p85: number; history_weeks: number[]; simulations: number;
    histogram: { week: number; probability: number }[]; target?: string; target_probability?: number;
  };
  burnup: { dates: string[]; scope: number[]; done: number[]; projection?: { p50: [string, number][]; p85: [string, number][] } };
}
interface RiskList { available: boolean; reason?: string; items: { id: string; title: string; owner: string; status: string; risk: number; factors: string[] }[]; }

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
            Plotline ran {{ f.simulations.toLocaleString() }} simulations, each replaying random weeks from your last
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
    <h3 class="section-title">Tickets most likely to slip</h3>
    <p class="note">A logistic regression trained on your finished tickets predicts which open tickets will miss their due date, using only facts known when each ticket was created.</p>
    @if (risk.data(); as r) {
      @if (!r.available) { <p class="note mt-3">{{ r.reason }}</p> } @else {
        <ul class="mt-3 divide-y divide-line/60">
          @for (t of r.items.slice(0, 12); track t.id) {
            <li class="flex gap-4 py-2.5 text-sm">
              <span class="w-12 shrink-0 font-display text-lg" [class.text-bad]="t.risk >= .6" [class.text-accent]="t.risk >= .35 && t.risk < .6" [class.text-ok]="t.risk < .35">{{ (t.risk * 100).toFixed(0) }}%</span>
              <div class="min-w-0"><p class="font-medium">{{ t.title }}</p><p class="text-muted">{{ t.owner || 'Unassigned' }} · {{ t.factors.join(' · ') || 'no single dominant factor' }}</p></div>
            </li>
          }
        </ul>
      }
    }
  </section>`,
})
export class ForecastView {
  readonly target = signal<string>('');
  readonly fc = projectResource<Forecast>((id) => `/projects/${id}/analytics/forecast`, (): Record<string, string> => (this.target() ? { target: this.target() } : {}));
  readonly risk = projectResource<RiskList>((id) => `/projects/${id}/analytics/risk`);
  readonly longDate = longDate; readonly pct = pct; readonly today = todayISO();

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
