import { Component, computed } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ChartComponent, baseOption } from '../../shared/chart.component';
import { RevealDirective } from '../../shared/motion';
import { duration } from './build.section';
import { projectResource } from './loader';

interface Group {
  delivered: number; open: number; on_time_rate: number | null; median_days: number | null;
  p10_days: number | null; p90_days: number | null; exception_rate: number | null;
}
interface Estimate { basis: string; n: number; p10: number; p50: number; p90: number; expected_by: string }
interface AtRisk {
  id: string; external_id: string | null; title: string; route: string; carrier: string; stage: string | null; due: string | null;
  age_days: number; risk: number | null; level: 'high' | 'medium' | 'low' | null; estimate: Estimate | null; reasons: string[];
}
interface Ship {
  available: boolean; reason: string;
  counts: { orders: number; delivered: number; open: number; exceptions_open: number; high_risk: number };
  on_time: { value: number | null; previous: number | null; all_time: number | null; recent_delivered: number };
  transit: { p50: number; p85: number; p95: number };
  weekly: { week: string; delivered: number; on_time_rate: number | null }[];
  dwell: { stage: string; label: string; n: number; median_hours: number | null; p85_hours: number | null }[];
  carriers: (Group & { carrier: string })[];
  routes: (Group & { route: string; promised_days: number | null })[];
  route_count: number;
  at_risk: AtRisk[];
  evaluation: {
    available: boolean; reason?: string; tested: number; coverage_p10_p90: number; mae_days: number; baseline_mae_days: number;
    risk_auc: number | null; baseline_auc: number | null;
  };
}

const TRACK = ['ordered', 'packed', 'dispatched', 'in_transit', 'out_for_delivery', 'delivered'];

@Component({
  selector: 'app-ship-section',
  imports: [ChartComponent, RouterLink, RevealDirective],
  template: `
  <section aria-labelledby="ship-title">
    <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
      <h2 id="ship-title" class="text-xl font-semibold">Orders and deliveries</h2>
      @if (data(); as s) { @if (s.available) {
        <span class="text-xs text-muted">{{ s.counts.delivered }} delivered · {{ s.counts.open }} on the way</span>
      } }
    </div>
    <p class="note mt-1">Whether orders arrive by the date you promised, which carriers and routes keep that promise, and which open orders probably won't.</p>

    @if (data(); as s) {
      @if (!s.available) {
        <div class="card mt-4 flex flex-wrap items-center gap-4">
          <svg width="52" height="36" viewBox="0 0 52 36" fill="none" aria-hidden="true" class="shrink-0">
            <rect x="2" y="8" width="28" height="18" rx="3" class="stroke-info" stroke-width="2.5"/>
            <path d="M30 13h10l8 7v6H30z" class="stroke-accent" stroke-width="2.5" stroke-linejoin="round"/>
            <circle cx="12" cy="29" r="4" class="fill-canvas stroke-muted" stroke-width="2.5"/><circle cx="40" cy="29" r="4" class="fill-canvas stroke-muted" stroke-width="2.5"/>
          </svg>
          <p class="flex-1 text-sm text-muted">{{ s.reason }}</p>
          <a routerLink="../live" class="btn">Get an API key</a>
        </div>
      } @else {
        <div appReveal class="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div class="card card-info anim-rise p-4" style="--i: 0">
            <p class="text-xs text-muted">On time, last 4 weeks</p>
            <p class="stat-value mt-2">{{ pct(s.on_time.value) }}</p>
            @if (trend(s); as t) {
              <p class="mt-2 text-xs" [class.text-ok]="t.good" [class.text-bad]="!t.good">{{ t.arrow }} {{ t.text }} <span class="text-muted">vs previous 4 weeks</span></p>
            } @else { <p class="mt-2 text-xs text-muted">Delivered on or before the promised date.</p> }
          </div>
          <div class="card card-info anim-rise p-4" style="--i: 1">
            <p class="text-xs text-muted">Typical delivery time</p>
            <p class="stat-value mt-2">{{ days(s.transit.p50) }}</p>
            <p class="mt-2 text-xs text-muted">From order to door. 85% arrive within {{ days(s.transit.p85) }}.</p>
          </div>
          <div class="card card-info anim-rise p-4" style="--i: 2">
            <p class="text-xs text-muted">On the way</p>
            <p class="stat-value mt-2">{{ s.counts.open }}</p>
            <p class="mt-2 text-xs" [class.text-bad]="s.counts.exceptions_open" [class.text-muted]="!s.counts.exceptions_open">
              {{ s.counts.exceptions_open ? s.counts.exceptions_open + ' had an exception on the way' : 'No exceptions open' }}</p>
          </div>
          <div class="card card-info anim-rise p-4" style="--i: 3">
            <p class="text-xs text-muted">Likely to arrive late</p>
            <p class="stat-value mt-2" [class.text-bad]="s.counts.high_risk">{{ s.counts.high_risk }}</p>
            <p class="mt-2 text-xs text-muted">Open orders with a 60% or higher chance of missing the promised date.</p>
          </div>
        </div>

        <div class="mt-4 grid gap-4 lg:grid-cols-[1.2fr_1fr]">
          <div class="card">
            <h3 class="section-title">On-time rate each week</h3>
            <p class="note mt-1">The line is the share delivered by the promised date; the bars are how many were delivered that week.</p>
            <app-chart class="mt-3 h-60" [options]="weeklyChart()" ariaLabel="Weekly on-time delivery rate and orders delivered"/>
          </div>
          <div class="card">
            <h3 class="section-title">Where orders wait</h3>
            <p class="note mt-1">Typical time between stages. The bar runs from the typical wait to the wait 85% of orders stayed within.</p>
            <ul class="mt-4 space-y-3">
              @for (d of s.dwell; track d.stage; let i = $index) {
                <li class="text-sm">
                  <div class="flex justify-between text-xs text-muted"><span class="text-fg">{{ d.label }}</span>
                    <span>{{ d.median_hours != null ? duration(d.median_hours) + ' – ' + duration(d.p85_hours) : 'no data yet' }}</span></div>
                  <svg viewBox="0 0 300 12" class="mt-1 h-3 w-full" preserveAspectRatio="none" aria-hidden="true">
                    <rect x="0" y="5" width="300" height="2" rx="1" class="fill-line"/>
                    @if (d.median_hours != null) {
                      <rect class="grow fill-violet/70" [style.animation-delay]="i * 90 + 'ms'" x="0" y="1"
                            [attr.width]="Math.max(4, x(d.median_hours))" height="10" rx="5"/>
                      <rect class="grow fill-violet/25" [style.animation-delay]="i * 90 + 'ms'" [attr.x]="x(d.median_hours)" y="1"
                            [attr.width]="Math.max(0, x(d.p85_hours ?? d.median_hours) - x(d.median_hours))" height="10" rx="5"/>
                    }
                  </svg>
                </li>
              }
            </ul>
          </div>
        </div>

        <div class="card mt-4">
          <h3 class="section-title">Orders likely to arrive late</h3>
          <p class="note mt-1">Open orders, riskiest first. The chance comes from how often orders on the same route, and the same carrier lately, missed their promise.</p>
          <ul class="mt-3 divide-y divide-line/70 text-sm">
            @for (o of s.at_risk.slice(0, 10); track o.id; let i = $index) {
              <li class="anim-rise grid gap-x-4 gap-y-1 py-2.5 sm:grid-cols-[minmax(0,1fr)_150px_96px]" [style.--i]="i">
                <div class="min-w-0">
                  <p class="truncate font-medium">{{ o.title }}</p>
                  <p class="text-xs text-muted">{{ o.carrier }} · {{ label(o.stage) }} · promised {{ o.due ?? '–' }}
                    @if (o.estimate) { · expected by {{ o.estimate.expected_by }} }</p>
                  @if (o.reasons.length) { <p class="mt-0.5 text-xs text-muted">{{ o.reasons.join(' · ') }}</p> }
                </div>
                <svg viewBox="0 0 150 16" class="h-4 w-full self-center" [attr.aria-label]="'Stage: ' + label(o.stage)" role="img">
                  <line x1="6" y1="8" x2="144" y2="8" class="stroke-line" stroke-width="2"/>
                  <line x1="6" y1="8" [attr.x2]="6 + step(o.stage) * 27.6" y2="8" class="track stroke-info" stroke-width="2" [style.animation-delay]="i * 60 + 'ms'"/>
                  @for (t of track; track t; let j = $index) {
                    <circle [attr.cx]="6 + j * 27.6" cy="8" r="4" stroke-width="2"
                            [class]="o.stage === 'exception' && j === step(o.stage) ? 'fill-bad stroke-bad' : j <= step(o.stage) ? 'fill-info stroke-info' : 'fill-canvas stroke-line'"/>
                  }
                </svg>
                <span class="self-center text-right">
                  @if (o.risk != null) {
                    <span class="pill" [class]="o.level === 'high' ? 'bg-bad/15 text-bad' : o.level === 'medium' ? 'bg-accent/15 text-accent' : 'bg-ok/10 text-ok-strong'">{{ (o.risk * 100).toFixed(0) }}% late</span>
                  } @else { <span class="text-xs text-muted">not enough data</span> }
                </span>
              </li>
            } @empty { <li class="py-2 text-muted">No orders on the way.</li> }
          </ul>
        </div>

        <div class="mt-4 grid gap-4 xl:grid-cols-2">
          <div class="card overflow-x-auto">
            <h3 class="section-title">Carriers</h3>
            <p class="note mt-1">Every carrier with at least 5 deliveries, most reliable first. "Took" is the range 8 in 10 deliveries fell within.</p>
            <table class="mt-3 w-full text-sm">
              <thead class="text-left text-xs text-muted"><tr><th class="py-1.5 font-medium">Carrier</th><th class="font-medium">On time</th><th class="text-right font-medium">Took</th><th class="text-right font-medium">Exceptions</th><th class="text-right font-medium">Open</th></tr></thead>
              <tbody>
                @for (c of s.carriers; track c.carrier) {
                  <tr class="border-t border-line/70">
                    <td class="py-2 pr-3">{{ c.carrier }} <span class="text-xs text-muted">· {{ c.delivered }}</span></td>
                    <td class="w-40 pr-3"><span class="flex items-center gap-2"><span class="h-1.5 flex-1 overflow-hidden rounded bg-line"><span class="grow-x block h-full rounded" [class]="bar(c.on_time_rate)" [style.width.%]="(c.on_time_rate ?? 0) * 100"></span></span><span class="w-9 text-right text-xs">{{ pct(c.on_time_rate) }}</span></span></td>
                    <td class="whitespace-nowrap text-right text-xs">{{ c.p10_days }}–{{ c.p90_days }} d</td>
                    <td class="text-right text-xs" [class.text-bad]="(c.exception_rate ?? 0) >= .06">{{ pct(c.exception_rate) }}</td>
                    <td class="text-right text-xs text-muted">{{ c.open }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
          <div class="card overflow-x-auto">
            <h3 class="section-title">Routes that miss the promise most</h3>
            <p class="note mt-1">Routes with at least 5 deliveries, worst first ({{ s.routes.length }} of {{ s.route_count }} shown). Compare what you promise with what it took.</p>
            <table class="mt-3 w-full text-sm">
              <thead class="text-left text-xs text-muted"><tr><th class="py-1.5 font-medium">Route</th><th class="text-right font-medium">Promised</th><th class="text-right font-medium">Took</th><th class="text-right font-medium">On time</th></tr></thead>
              <tbody>
                @for (r of s.routes; track r.route) {
                  <tr class="border-t border-line/70">
                    <td class="py-2 pr-3">{{ r.route }} <span class="text-xs text-muted">· {{ r.delivered }}</span></td>
                    <td class="text-right text-xs">{{ r.promised_days ?? '–' }} d</td>
                    <td class="whitespace-nowrap text-right text-xs" [class.text-bad]="r.promised_days != null && (r.p90_days ?? 0) > r.promised_days + 1">{{ r.p10_days }}–{{ r.p90_days }} d</td>
                    <td class="text-right text-xs" [class.text-bad]="(r.on_time_rate ?? 1) < .7" [class.text-ok]="(r.on_time_rate ?? 0) >= .9">{{ pct(r.on_time_rate) }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        </div>

        @if (s.evaluation.available) {
          <p class="note mt-4 rounded-lg border border-line/70 bg-canvas/50 px-4 py-3">
            <span class="font-medium text-fg">How good are these estimates?</span>
            Back-tested on the newest {{ s.evaluation.tested }} delivered orders, each estimated only from orders delivered before it was placed:
            the "took" range held {{ pct(s.evaluation.coverage_p10_p90) }} of the time (aim: about 80%), and the typical estimate was off by
            {{ s.evaluation.mae_days }} days, against {{ s.evaluation.baseline_mae_days }} for "the usual delivery time".
            @if (s.evaluation.risk_auc != null) {
              Late risk ranked late orders above on-time ones {{ pct(s.evaluation.risk_auc) }} of the time, against {{ pct(s.evaluation.baseline_auc) }} using only the carrier's record.
            }
          </p>
        }
      }
    } @else if (res.error()) { <p class="mt-4 text-sm text-bad">{{ res.error() }}</p> }
    @else { <div class="mt-4 grid gap-3 sm:grid-cols-4">@for (i of [0, 1, 2, 3]; track i) { <div class="skeleton h-28"></div> }</div> }
  </section>`,
  styles: [`
    .grow { transform-box: fill-box; transform-origin: left center; animation: grow-bar .8s cubic-bezier(.2,.8,.2,1) backwards; }
    .grow-x { transform-origin: left center; animation: grow-bar .8s cubic-bezier(.2,.8,.2,1) backwards; }
    .track { stroke-dasharray: 140; stroke-dashoffset: 0; animation: draw-track .9s ease-out backwards; }
    @keyframes grow-bar { from { transform: scaleX(0); } }
    @keyframes draw-track { from { stroke-dashoffset: 140; } }
    @media (prefers-reduced-motion: reduce) { .grow, .grow-x, .track { animation: none; } }
  `],
})
export class ShipSection {
  readonly res = projectResource<Ship>((id) => `/projects/${id}/analytics/ship`);
  readonly data = this.res.data;
  readonly duration = duration;
  readonly Math = Math;
  readonly track = TRACK;

  private readonly maxHours = computed(() => Math.max(1, ...(this.data()?.dwell ?? []).map((d) => d.p85_hours ?? 0)));
  x(hours: number) { return (hours / this.maxHours()) * 300; }

  pct(v: number | null | undefined) { return v == null ? '–' : `${Math.round(v * 100)}%`; }
  days(v: number | null | undefined) { return v == null ? '–' : `${v} day${v === 1 ? '' : 's'}`; }
  label(stage: string | null) { if (!stage) return 'No stage'; const t = stage.replace(/_/g, ' '); return t.charAt(0).toUpperCase() + t.slice(1); }
  /** Position on the order track; an exception sits where the parcel was, in transit. */
  step(stage: string | null) { if (stage === 'exception') return 3; return Math.max(0, TRACK.indexOf(stage ?? 'ordered')); }
  bar(rate: number | null) { return (rate ?? 0) >= 0.9 ? 'bg-ok/80' : (rate ?? 0) >= 0.75 ? 'bg-accent/80' : 'bg-bad/80'; }

  trend(s: Ship): { arrow: string; text: string; good: boolean } | null {
    const { value, previous } = s.on_time;
    if (value == null || previous == null) return null;
    const pts = Math.round(value * 100) - Math.round(previous * 100);  // the same rounding as the shown percentages
    if (pts === 0) return null;
    return { arrow: pts > 0 ? '▲' : '▼', text: `${Math.abs(pts)} pts`, good: pts > 0 };
  }

  readonly weeklyChart = computed(() => {
    const w = this.data()?.weekly ?? [];
    const axis = { color: '#A3AEC4' };
    return baseOption({
      grid: { left: 44, right: 36, top: 24, bottom: 28, containLabel: false },
      xAxis: { type: 'category', data: w.map((x) => x.week.slice(5)), axisLabel: axis },
      yAxis: [
        { type: 'value', min: 0, max: 100, axisLabel: { ...axis, formatter: '{value}%' }, splitLine: { lineStyle: { color: '#2A3650' } } },
        { type: 'value', minInterval: 1, axisLabel: axis, splitLine: { show: false } },
      ],
      series: [
        { name: 'Delivered', type: 'bar', yAxisIndex: 1, data: w.map((x) => x.delivered), itemStyle: { color: 'rgba(110,168,254,.28)', borderRadius: [4, 4, 0, 0] } },
        {
          name: 'On time', type: 'line', smooth: true, connectNulls: true, symbolSize: 7,
          data: w.map((x) => (x.on_time_rate == null ? null : Math.round(x.on_time_rate * 100))),
          lineStyle: { width: 3, color: '#4FD1A5' }, itemStyle: { color: '#4FD1A5' },
        },
      ],
    });
  });
}
