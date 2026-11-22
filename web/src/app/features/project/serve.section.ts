import { Component, computed } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ChartComponent, baseOption } from '../../shared/chart.component';
import { RevealDirective } from '../../shared/motion';
import { duration } from './build.section';
import { projectResource } from './loader';

interface Group {
  visits: number; on_time_rate: number | null; rescheduled_rate: number | null; median_hours: number | null;
  p10_hours: number | null; p90_hours: number | null; vs_estimate: number | null; estimate_hours: number | null;
}
interface Upcoming {
  id: string; external_id: string | null; title: string; tech: string; area: string; service: string; stage: string | null;
  window_start: string | null; window_end: string | null; load: number; estimate: number | null;
  duration: { basis: string; n: number; p10: number; p50: number; p90: number } | null;
  risk: number | null; level: 'high' | 'medium' | 'low' | null; reasons: string[];
}
interface Serve {
  available: boolean; reason: string;
  counts: { jobs: number; visits: number; done: number; upcoming: number; high_risk: number; rescheduled: number; cancelled: number };
  on_time: { value: number | null; previous: number | null; all_time: number | null };
  duration: { p50: number; p85: number };
  weekly: { week: string; visits: number; on_time_rate: number | null; rescheduled: number }[];
  dwell: { stage: string; label: string; n: number; median_hours: number | null; p85_hours: number | null }[];
  load: { band: string; label: string; visits: number; missed_rate: number | null }[];
  technicians: (Group & { tech: string; upcoming: number; upcoming_hours: number; busiest_day: string | null; busiest_jobs: number })[];
  areas: (Group & { area: string })[];
  services: (Group & { service: string })[];
  upcoming: Upcoming[];
  evaluation: {
    available: boolean; tested: number; risk_auc: number; baseline_auc: number; duration_tested: number;
    coverage_p10_p90: number | null; mae_hours: number | null; baseline_mae_hours: number | null;
  };
}

@Component({
  selector: 'app-serve-section',
  imports: [ChartComponent, RouterLink, RevealDirective],
  template: `
  <section aria-labelledby="serve-title">
    <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
      <h2 id="serve-title" class="text-xl font-semibold">Visits and technicians</h2>
      @if (data(); as s) { @if (s.available) {
        <span class="text-xs text-muted">{{ s.counts.visits }} visits · {{ s.counts.upcoming }} coming up in the next 7 days</span>
      } }
    </div>
    <p class="note mt-1">Whether technicians arrive within the appointment window, how long jobs really take against what was booked, and which upcoming visits are likely to be missed.</p>

    @if (data(); as s) {
      @if (!s.available) {
        <div class="card mt-4 flex flex-wrap items-center gap-4">
          <svg width="44" height="44" viewBox="0 0 44 44" fill="none" aria-hidden="true" class="shrink-0">
            <circle cx="22" cy="22" r="17" class="stroke-info" stroke-width="2.5"/>
            <path d="M22 12v10l7 4" class="stroke-accent" stroke-width="2.5" stroke-linecap="round"/>
          </svg>
          <p class="flex-1 text-sm text-muted">{{ s.reason }}</p>
          <a routerLink="../live" class="btn">Get an API key</a>
        </div>
      } @else {
        <div appReveal class="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div class="card card-info anim-rise p-4" style="--i: 0">
            <p class="text-xs text-muted">Arrived on time, last 4 weeks</p>
            <p class="stat-value mt-2">{{ pct(s.on_time.value) }}</p>
            @if (trend(s); as t) {
              <p class="mt-2 text-xs" [class.text-ok]="t.good" [class.text-bad]="!t.good">{{ t.arrow }} {{ t.text }} <span class="text-muted">vs previous 4 weeks</span></p>
            } @else { <p class="mt-2 text-xs text-muted">Within the window, and not rescheduled.</p> }
          </div>
          <div class="card card-info anim-rise p-4" style="--i: 1">
            <p class="text-xs text-muted">Typical job length</p>
            <p class="stat-value mt-2">{{ duration(s.duration.p50) }}</p>
            <p class="mt-2 text-xs text-muted">On site to done. 85% finish within {{ duration(s.duration.p85) }}.</p>
          </div>
          <div class="card card-info anim-rise p-4" style="--i: 2">
            <p class="text-xs text-muted">Visits in the next 7 days</p>
            <p class="stat-value mt-2">{{ s.counts.upcoming }}</p>
            <p class="mt-2 text-xs text-muted">{{ s.counts.rescheduled }} rescheduled and {{ s.counts.cancelled }} cancelled so far.</p>
          </div>
          <div class="card card-info anim-rise p-4" style="--i: 3">
            <p class="text-xs text-muted">Likely to be missed</p>
            <p class="stat-value mt-2" [class.text-bad]="s.counts.high_risk">{{ s.counts.high_risk }}</p>
            <p class="mt-2 text-xs text-muted">Upcoming visits with a 50% or higher chance of a late arrival or reschedule.</p>
          </div>
        </div>

        <div class="card mt-4">
          <h3 class="section-title">Visits likely to be missed</h3>
          <p class="note mt-1">Upcoming visits, riskiest first. The chance comes from the technician's last 6 weeks, how busy their day is, and the time of day.</p>
          <ul class="mt-3 divide-y divide-line/70 text-sm">
            @for (j of s.upcoming.slice(0, 10); track j.id; let i = $index) {
              <li class="anim-rise grid gap-x-4 gap-y-1 py-2.5 sm:grid-cols-[minmax(0,1fr)_120px_96px]" [style.--i]="i">
                <div class="min-w-0">
                  <p class="truncate font-medium">{{ j.title }}</p>
                  <p class="text-xs text-muted">{{ j.tech || 'No technician' }} · {{ when(j.window_start, j.window_end) }} · {{ label(j.stage) }}
                    @if (j.duration) { · likely {{ j.duration.p10 }}–{{ j.duration.p90 }} h }</p>
                  @if (j.reasons.length) { <p class="mt-0.5 text-xs text-muted">{{ j.reasons.join(' · ') }}</p> }
                </div>
                <span class="self-center text-xs" [title]="j.load + ' jobs that day for ' + j.tech">
                  <span class="flex gap-1" aria-hidden="true">
                    @for (n of dots(j.load); track $index) { <span class="h-2.5 w-2.5 rounded-full" [class]="j.load >= 4 ? 'bg-bad/80' : j.load === 3 ? 'bg-accent/80' : 'bg-info/70'"></span> }
                  </span>
                  <span class="text-muted">{{ j.load }} job{{ j.load === 1 ? '' : 's' }} that day</span>
                </span>
                <span class="self-center text-right">
                  @if (j.risk != null) {
                    <span class="pill" [class]="j.level === 'high' ? 'bg-bad/15 text-bad' : j.level === 'medium' ? 'bg-accent/15 text-accent' : 'bg-ok/10 text-ok-strong'">{{ (j.risk * 100).toFixed(0) }}% missed</span>
                  } @else { <span class="text-xs text-muted">not enough data</span> }
                </span>
              </li>
            } @empty { <li class="py-2 text-muted">No visits booked for the next 7 days.</li> }
          </ul>
        </div>

        <div class="mt-4 grid gap-4 lg:grid-cols-[1.2fr_1fr]">
          <div class="card">
            <h3 class="section-title">On-time arrivals each week</h3>
            <p class="note mt-1">The line is the share of visits that arrived within the window; the bars are how many visits there were.</p>
            <app-chart class="mt-3 h-60" [options]="weeklyChart()" ariaLabel="Weekly on-time arrival rate and number of visits"/>
          </div>
          <div class="card">
            <h3 class="section-title">Busy days run late</h3>
            <p class="note mt-1">Share of visits missed, by how many jobs the technician had that day.</p>
            <svg viewBox="0 0 300 170" class="mt-4 w-full" role="img" aria-label="Missed-visit rate by technician load">
              @for (b of s.load; track b.band; let i = $index) {
                <g [attr.transform]="'translate(' + (24 + i * 92) + ',0)'">
                  <rect x="0" y="20" width="60" height="110" rx="6" class="fill-line/50"/>
                  <rect class="rise" [style.animation-delay]="i * 120 + 'ms'" x="0" [attr.y]="130 - 110 * (b.missed_rate ?? 0)" width="60"
                        [attr.height]="110 * (b.missed_rate ?? 0)" rx="6" [attr.class]="'rise ' + (b.band === 'heavy' ? 'fill-bad/80' : b.band === 'normal' ? 'fill-accent/80' : 'fill-info/70')"/>
                  <text x="30" [attr.y]="122 - 110 * (b.missed_rate ?? 0)" text-anchor="middle" class="fill-fg text-[13px] font-semibold">{{ pct(b.missed_rate) }}</text>
                  <text x="30" y="148" text-anchor="middle" class="fill-muted text-[11px]">{{ b.label }}</text>
                  <text x="30" y="163" text-anchor="middle" class="fill-muted text-[10px]">{{ b.visits }} visits</text>
                </g>
              }
            </svg>
          </div>
        </div>

        <div class="mt-4 grid gap-4 xl:grid-cols-2">
          <div class="card overflow-x-auto">
            <h3 class="section-title">Technicians</h3>
            <p class="note mt-1">Most punctual first. "Took vs booked" compares real job length with the hours booked (1.0× means spot on).</p>
            <table class="mt-3 w-full text-sm">
              <thead class="text-left text-xs text-muted"><tr><th class="py-1.5 font-medium">Technician</th><th class="font-medium">On time</th><th class="text-right font-medium">Took vs booked</th><th class="text-right font-medium">Next 7 days</th></tr></thead>
              <tbody>
                @for (t of s.technicians; track t.tech) {
                  <tr class="border-t border-line/70">
                    <td class="py-2 pr-3">{{ t.tech }} <span class="text-xs text-muted">· {{ t.visits }}</span></td>
                    <td class="w-40 pr-3"><span class="flex items-center gap-2"><span class="h-1.5 flex-1 overflow-hidden rounded bg-line"><span class="grow-x block h-full rounded" [class]="bar(t.on_time_rate)" [style.width.%]="(t.on_time_rate ?? 0) * 100"></span></span><span class="w-9 text-right text-xs">{{ pct(t.on_time_rate) }}</span></span></td>
                    <td class="text-right text-xs" [class.text-bad]="(t.vs_estimate ?? 0) > 1.2">{{ t.vs_estimate ?? '–' }}×</td>
                    <td class="whitespace-nowrap text-right text-xs text-muted">{{ t.upcoming }} jobs · {{ t.upcoming_hours }} h
                      @if (t.busiest_jobs >= 3) { <span class="block text-bad">{{ t.busiest_jobs }} on {{ shortDay(t.busiest_day) }}</span> }</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
          <div class="card overflow-x-auto">
            <h3 class="section-title">Services: booked vs real length</h3>
            <p class="note mt-1">Services that run longest over their booking first. "Took" is the range 8 in 10 jobs fell within.</p>
            <table class="mt-3 w-full text-sm">
              <thead class="text-left text-xs text-muted"><tr><th class="py-1.5 font-medium">Service</th><th class="text-right font-medium">Booked</th><th class="text-right font-medium">Took</th><th class="text-right font-medium">Rescheduled</th></tr></thead>
              <tbody>
                @for (v of s.services; track v.service) {
                  <tr class="border-t border-line/70">
                    <td class="py-2 pr-3">{{ v.service }} <span class="text-xs text-muted">· {{ v.visits }}</span></td>
                    <td class="text-right text-xs">{{ v.estimate_hours ?? '–' }} h</td>
                    <td class="whitespace-nowrap text-right text-xs" [class.text-bad]="(v.vs_estimate ?? 0) > 1.2">{{ v.p10_hours }}–{{ v.p90_hours }} h</td>
                    <td class="text-right text-xs" [class.text-bad]="(v.rescheduled_rate ?? 0) >= .1">{{ pct(v.rescheduled_rate) }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        </div>

        <div class="mt-4 grid gap-4 lg:grid-cols-[1fr_1.1fr]">
          <div class="card overflow-x-auto">
            <h3 class="section-title">Areas</h3>
            <p class="note mt-1">Areas where visits arrive late most often, first.</p>
            <table class="mt-3 w-full text-sm">
              <thead class="text-left text-xs text-muted"><tr><th class="py-1.5 font-medium">Area</th><th class="text-right font-medium">Visits</th><th class="text-right font-medium">On time</th><th class="text-right font-medium">Rescheduled</th></tr></thead>
              <tbody>
                @for (a of s.areas; track a.area) {
                  <tr class="border-t border-line/70">
                    <td class="py-2 pr-3">{{ a.area }}</td><td class="text-right text-xs text-muted">{{ a.visits }}</td>
                    <td class="text-right text-xs" [class.text-bad]="(a.on_time_rate ?? 1) < .75" [class.text-ok]="(a.on_time_rate ?? 0) >= .9">{{ pct(a.on_time_rate) }}</td>
                    <td class="text-right text-xs">{{ pct(a.rescheduled_rate) }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
          <div class="card">
            <h3 class="section-title">Where jobs wait</h3>
            <p class="note mt-1">Typical time between stages. The bar runs from the typical wait to the wait 85% of jobs stayed within.</p>
            <ul class="mt-4 space-y-3">
              @for (d of s.dwell; track d.stage; let i = $index) {
                <li class="text-sm">
                  <div class="flex justify-between text-xs text-muted"><span class="text-fg">{{ d.label }}</span>
                    <span>{{ d.median_hours != null ? duration(d.median_hours) + ' – ' + duration(d.p85_hours) : 'no data yet' }}</span></div>
                  <svg viewBox="0 0 300 12" class="mt-1 h-3 w-full" preserveAspectRatio="none" aria-hidden="true">
                    <rect x="0" y="5" width="300" height="2" rx="1" class="fill-line"/>
                    @if (d.median_hours != null) {
                      <rect class="grow fill-violet/70" [style.animation-delay]="i * 90 + 'ms'" x="0" y="1" [attr.width]="Math.max(4, x(d.median_hours))" height="10" rx="5"/>
                      <rect class="grow fill-violet/25" [style.animation-delay]="i * 90 + 'ms'" [attr.x]="x(d.median_hours)" y="1"
                            [attr.width]="Math.max(0, x(d.p85_hours ?? d.median_hours) - x(d.median_hours))" height="10" rx="5"/>
                    }
                  </svg>
                </li>
              }
            </ul>
          </div>
        </div>

        @if (s.evaluation.available) {
          <p class="note mt-4 rounded-lg border border-line/70 bg-canvas/50 px-4 py-3">
            <span class="font-medium text-fg">How good are these estimates?</span>
            Back-tested on the newest {{ s.evaluation.tested }} visits, each judged only from visits finished before it:
            missed-visit risk ranked missed visits above on-time ones {{ pct(s.evaluation.risk_auc) }} of the time, against {{ pct(s.evaluation.baseline_auc) }} using only the technician's record.
            @if (s.evaluation.mae_hours != null) {
              Job lengths were off by {{ s.evaluation.mae_hours }} h on average, against {{ s.evaluation.baseline_mae_hours }} h for the hours booked,
              and the "took" range held {{ pct(s.evaluation.coverage_p10_p90) }} of the time (aim: about 80%).
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
    .rise { transform-box: fill-box; transform-origin: center bottom; animation: rise-bar .9s cubic-bezier(.2,.8,.2,1) backwards; }
    @keyframes grow-bar { from { transform: scaleX(0); } }
    @keyframes rise-bar { from { transform: scaleY(0); } }
    @media (prefers-reduced-motion: reduce) { .grow, .grow-x, .rise { animation: none; } }
  `],
})
export class ServeSection {
  readonly res = projectResource<Serve>((id) => `/projects/${id}/analytics/serve`);
  readonly data = this.res.data;
  readonly duration = duration;
  readonly Math = Math;

  private readonly maxHours = computed(() => Math.max(1, ...(this.data()?.dwell ?? []).map((d) => d.p85_hours ?? 0)));
  x(hours: number) { return (hours / this.maxHours()) * 300; }

  pct(v: number | null | undefined) { return v == null ? '–' : `${Math.round(v * 100)}%`; }
  label(stage: string | null) { if (!stage) return 'No stage'; const t = stage.replace(/_/g, ' '); return t.charAt(0).toUpperCase() + t.slice(1); }
  bar(rate: number | null) { return (rate ?? 0) >= 0.9 ? 'bg-ok/80' : (rate ?? 0) >= 0.75 ? 'bg-accent/80' : 'bg-bad/80'; }
  dots(n: number) { return Array.from({ length: Math.min(n, 6) }); }
  shortDay(iso: string | null) { return iso ? new Date(iso + 'T00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' }) : ''; }

  /** "Tue 24 Nov, 14:00–16:00" in the viewer's local time. */
  when(start: string | null, end: string | null) {
    if (!start) return 'no window set';
    const s = new Date(start), e = end ? new Date(end) : null;
    const t = (d: Date) => d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false });
    return `${s.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })}, ${t(s)}${e ? '–' + t(e) : ''}`;
  }

  trend(s: Serve): { arrow: string; text: string; good: boolean } | null {
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
        { name: 'Visits', type: 'bar', yAxisIndex: 1, data: w.map((x) => x.visits), itemStyle: { color: 'rgba(167,139,250,.28)', borderRadius: [4, 4, 0, 0] } },
        {
          name: 'On time', type: 'line', smooth: true, connectNulls: true, symbolSize: 7,
          data: w.map((x) => (x.on_time_rate == null ? null : Math.round(x.on_time_rate * 100))),
          lineStyle: { width: 3, color: '#4FD1A5' }, itemStyle: { color: '#4FD1A5' },
        },
      ],
    });
  });
}
