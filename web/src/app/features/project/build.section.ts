import { Component, computed } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ChartComponent, baseOption } from '../../shared/chart.component';
import { RevealDirective } from '../../shared/motion';
import { projectResource } from './loader';

interface Metric { value: number | null; previous: number | null; unit: 'per_week' | 'hours' | 'percent'; note: string; }
interface Build {
  available: boolean; reason: string;
  counts: { prs: number; deploys: number; releases: number };
  review: {
    median_hours: number | null; p85_hours: number | null; reviewed: number; waiting_count: number;
    weekly: { week: string; median: number | null; n: number }[];
  };
  sizes: {
    classes: { size: string; lines: string; n: number; p50_hours: number | null; p85_hours: number | null }[];
    open: { title: string; number: number | null; url: string | null; size: string | null; author: string; age_hours: number; expected: [number, number] | null }[];
    open_count: number;
  };
  dora: {
    source: 'deployments' | 'releases';
    deployment_frequency: Metric; lead_time: Metric; change_failure_rate: Metric; recovery_time: Metric;
    weekly: { week: string; ok: number; failed: number }[];
  };
}

/** "Lower is better" for everything except how often you ship. */
const DORA: { key: 'deployment_frequency' | 'lead_time' | 'change_failure_rate' | 'recovery_time'; label: string; up: boolean; help: string }[] = [
  { key: 'deployment_frequency', label: 'Deployments', up: true, help: 'Successful production deployments a week.' },
  { key: 'lead_time', label: 'Lead time', up: false, help: 'How long a change takes to reach production.' },
  { key: 'change_failure_rate', label: 'Failed deployments', up: false, help: 'Share of deployments that failed.' },
  { key: 'recovery_time', label: 'Recovery time', up: false, help: 'How long it took to fix a failed deployment.' },
];

export function duration(hours: number | null | undefined): string {
  if (hours == null) return '–';
  if (hours < 1) return 'under 1 h';
  if (hours < 48) return `${Math.round(hours)} h`;
  return `${(hours / 24).toFixed(hours < 240 ? 1 : 0)} days`;
}

@Component({
  selector: 'app-build-section',
  imports: [ChartComponent, RouterLink, RevealDirective],
  template: `
  <section class="mt-10" aria-labelledby="build-title">
    <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
      <h2 id="build-title" class="text-xl font-semibold">Pull requests and releases</h2>
      @if (data(); as b) { @if (b.available) {
        <span class="text-xs text-muted">{{ b.counts.prs }} pull requests · {{ b.counts.deploys }} deployments · {{ b.counts.releases }} releases, from GitHub</span>
      } }
    </div>
    <p class="note mt-1">How quickly code gets reviewed, merged and shipped. The four delivery numbers are the DORA metrics, over the last 4 weeks.</p>

    @if (data(); as b) {
      @if (!b.available) {
        <div class="card mt-4 flex flex-wrap items-center gap-4">
          <svg width="44" height="44" viewBox="0 0 44 44" fill="none" aria-hidden="true" class="shrink-0">
            <circle cx="12" cy="12" r="5" class="stroke-info" stroke-width="2.5"/><circle cx="12" cy="34" r="5" class="stroke-info" stroke-width="2.5"/>
            <circle cx="32" cy="22" r="5" class="stroke-accent" stroke-width="2.5"/>
            <path d="M12 17v12M12 22c0-6 8-6 15 0" class="flow-line stroke-muted" stroke-width="2.5" stroke-linecap="round"/>
          </svg>
          <p class="flex-1 text-sm text-muted">{{ b.reason }}</p>
          <a routerLink="../live" class="btn">Connect GitHub</a>
        </div>
      } @else {
        <!-- DORA cards -->
        <div appReveal class="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          @for (m of dora; track m.key; let i = $index) {
            <div class="card card-info anim-rise p-4" [style.--i]="i" [title]="b.dora[m.key].note || m.help">
              <p class="text-xs text-muted">{{ m.label }}</p>
              <p class="stat-value mt-2">{{ show(b.dora[m.key]) }}</p>
              @if (trend(b.dora[m.key], m.up); as t) {
                <p class="mt-2 text-xs" [class.text-ok]="t.good" [class.text-bad]="!t.good">{{ t.arrow }} {{ t.text }} <span class="text-muted">vs previous 4 weeks</span></p>
              } @else { <p class="mt-2 text-xs text-muted">{{ m.help }}</p> }
              @if (b.dora[m.key].note) { <p class="mt-1 text-[11px] leading-snug text-muted">{{ b.dora[m.key].note }}</p> }
            </div>
          }
        </div>

        <div class="mt-4 grid gap-4 lg:grid-cols-2">
          <div class="card">
            <h3 class="section-title">{{ b.dora.source === 'releases' ? 'Releases' : 'Deployments' }} each week</h3>
            <p class="note mt-1">Each bar is one week; the red part is deployments that failed.</p>
            <app-chart class="mt-3 h-56" [options]="deployChart()" ariaLabel="Deployments per week, split into successful and failed"/>
          </div>
          <div class="card">
            <h3 class="section-title">Waiting for a first review</h3>
            <p class="note mt-1">The typical wait each week, in hours. Half of pull requests waited {{ duration(b.review.median_hours) }} or less; 85% within {{ duration(b.review.p85_hours) }}.</p>
            <app-chart class="mt-3 h-56" [options]="reviewChart()" ariaLabel="Median hours waiting for a first review, by week"/>
          </div>
        </div>

        <div class="mt-4 grid gap-4 lg:grid-cols-[1.1fr_1fr]">
          <div class="card">
            <h3 class="section-title">How long pull requests take to merge, by size</h3>
            <p class="note mt-1">From opened to merged. The bar runs from the typical time to the time 85% finished within.</p>
            <ul class="mt-4 space-y-3">
              @for (c of b.sizes.classes; track c.size; let i = $index) {
                <li class="grid grid-cols-[2.5rem_1fr] items-center gap-3 text-sm">
                  <span class="pill justify-center bg-raised font-semibold">{{ c.size }}</span>
                  <div>
                    <div class="flex justify-between text-xs text-muted"><span>{{ c.lines }} · {{ c.n }} merged</span>
                      <span>{{ c.p50_hours != null ? duration(c.p50_hours) + ' – ' + duration(c.p85_hours) : 'not enough yet' }}</span></div>
                    <svg viewBox="0 0 300 12" class="mt-1 h-3 w-full" preserveAspectRatio="none" aria-hidden="true">
                      <rect x="0" y="5" width="300" height="2" rx="1" class="fill-line"/>
                      @if (c.p50_hours != null) {
                        <rect class="size-bar fill-info/70" [style.animation-delay]="i * 90 + 'ms'"
                              [attr.x]="x(c.p50_hours)" y="1" [attr.width]="Math.max(4, x(c.p85_hours!) - x(c.p50_hours))" height="10" rx="5"/>
                      }
                    </svg>
                  </div>
                </li>
              }
            </ul>
          </div>
          <div class="card">
            <h3 class="section-title">Open pull requests</h3>
            <p class="note mt-1">{{ b.sizes.open_count }} open, {{ b.review.waiting_count }} still waiting for a first review. Similar-size PRs give the expected time.</p>
            <ul class="mt-3 divide-y divide-line/70 text-sm">
              @for (p of b.sizes.open; track p.title + p.number) {
                <li class="flex items-center gap-3 py-2">
                  <span class="pill bg-raised text-muted">{{ p.size ?? '?' }}</span>
                  <span class="min-w-0 flex-1">
                    @if (p.url) { <a [href]="p.url" target="_blank" rel="noopener" class="block truncate hover:underline">{{ p.title }}</a> }
                    @else { <span class="block truncate">{{ p.title }}</span> }
                    <span class="text-xs text-muted">{{ p.author }}{{ p.number ? ' · #' + p.number : '' }} · open {{ duration(p.age_hours) }}</span>
                  </span>
                  @if (p.expected) {
                    <span class="shrink-0 text-right text-xs" [class.text-bad]="p.age_hours > p.expected[1]" [class.text-muted]="p.age_hours <= p.expected[1]">
                      PRs this size: {{ duration(p.expected[0]) }}–{{ duration(p.expected[1]) }}
                    </span>
                  }
                </li>
              } @empty { <li class="py-2 text-muted">No open pull requests.</li> }
            </ul>
          </div>
        </div>
      }
    } @else if (res.error()) { <p class="mt-4 text-sm text-bad">{{ res.error() }}</p> }
    @else { <div class="mt-4 grid gap-3 sm:grid-cols-4">@for (i of [0, 1, 2, 3]; track i) { <div class="skeleton h-28"></div> }</div> }
  </section>`,
  styles: [`
    .size-bar { transform-box: fill-box; transform-origin: left center; animation: grow-bar .8s cubic-bezier(.2,.8,.2,1) backwards; }
    @keyframes grow-bar { from { transform: scaleX(0); } }
    @media (prefers-reduced-motion: reduce) { .size-bar { animation: none; } }
  `],
})
export class BuildSection {
  readonly res = projectResource<Build>((id) => `/projects/${id}/analytics/build`);
  readonly data = this.res.data;
  readonly dora = DORA;
  readonly duration = duration;
  readonly Math = Math;

  /** Size bars share one scale: the slowest class's 85% time. */
  private readonly maxHours = computed(() => Math.max(1, ...(this.data()?.sizes?.classes ?? []).map((c) => c.p85_hours ?? 0)));
  x(hours: number) { return (hours / this.maxHours()) * 300; }

  show(m: Metric): string {
    if (m.value == null) return '–';
    if (m.unit === 'per_week') return `${m.value} / wk`;
    if (m.unit === 'percent') return `${m.value}%`;
    return duration(m.value);
  }

  trend(m: Metric, upIsGood: boolean): { arrow: string; text: string; good: boolean } | null {
    if (m.value == null || m.previous == null || m.value === m.previous) return null;
    const up = m.value > m.previous;
    const diff = m.unit === 'percent' ? `${Math.abs(m.value - m.previous).toFixed(1)} pts`
      : m.unit === 'per_week' ? `${Math.abs(m.value - m.previous).toFixed(1)} / wk` : duration(Math.abs(m.value - m.previous));
    return { arrow: up ? '▲' : '▼', text: diff, good: up === upIsGood };
  }

  readonly deployChart = computed(() => {
    const w = this.data()?.dora.weekly ?? [];
    return baseOption({
      xAxis: { type: 'category', data: w.map((x) => x.week.slice(5)), axisLabel: { color: '#A3AEC4' } },
      yAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: '#2A3650' } }, axisLabel: { color: '#A3AEC4' } },
      series: [
        { name: 'Succeeded', type: 'bar', stack: 'd', data: w.map((x) => x.ok), itemStyle: { color: '#4FD1A5', borderRadius: [0, 0, 0, 0] } },
        { name: 'Failed', type: 'bar', stack: 'd', data: w.map((x) => x.failed), itemStyle: { color: '#FF7A7A', borderRadius: [4, 4, 0, 0] } },
      ],
    });
  });

  readonly reviewChart = computed(() => {
    const w = this.data()?.review.weekly ?? [];
    return baseOption({
      xAxis: { type: 'category', data: w.map((x) => x.week.slice(5)), axisLabel: { color: '#A3AEC4' } },
      yAxis: { type: 'value', name: 'hours', nameTextStyle: { color: '#A3AEC4' }, splitLine: { lineStyle: { color: '#2A3650' } }, axisLabel: { color: '#A3AEC4' } },
      series: [{
        type: 'line', smooth: true, connectNulls: true, symbolSize: 7, data: w.map((x) => x.median),
        lineStyle: { width: 3, color: '#6EA8FE' }, itemStyle: { color: '#6EA8FE' },
        areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(110,168,254,.35)' }, { offset: 1, color: 'rgba(110,168,254,0)' }] } },
      }],
    });
  });
}
