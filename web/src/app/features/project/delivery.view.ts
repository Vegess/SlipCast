import { NgClass } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { Api, errorMessage } from '../../core/api.service';
import { ProjectContext } from './project.context';
import { KIND_LABEL } from '../../core/models';
import { ChartComponent, PALETTE, baseOption } from '../../shared/chart.component';
import { longDate, num, pct } from '../../shared/format';
import { projectResource } from './loader';

interface Breakdown { key: string; open: number; done: number; median_cycle_days: number | null; p85_cycle_days: number | null; slip_rate: number | null; }
interface Flow {
  available: boolean; reason: string;
  cycle_time: { percentiles: { p50: number; p85: number; p95: number }; points: { id: string; title: string; date: string; days: number; kind: string }[] };
  throughput: { weeks: string[]; counts: number[] };
  cfd: { dates: string[]; series: Record<string, number[]> };
  by_kind: Breakdown[]; by_topic: Breakdown[]; by_owner: Breakdown[];
  aging: { id: string; title: string; owner: string; status: string; age_days: number; over_p85: boolean }[];
}
interface Overview { open: number; done: number; tickets: number; cycle: { p50: number; p85: number }; throughput_avg: number; forecast_p85: string | null; high_risk: number | null; }

@Component({
  selector: 'app-delivery-view',
  imports: [ChartComponent, NgClass],
  template: `
  <div class="mb-5 flex flex-wrap items-center gap-2">
    <p class="note mr-auto">How work flows through this project. Export the same numbers to analyse them elsewhere.</p>
    <button class="btn" (click)="download('export.xlsx', 'slipcast.xlsx')" [disabled]="busy()">Export to Excel</button>
    <button class="btn" (click)="download('export/bi.zip', 'slipcast-bi.zip')" [disabled]="busy()">Export for Tableau / Power BI</button>
  </div>
  @if (exportError()) { <p class="mb-3 text-sm text-bad">{{ exportError() }}</p> }
  @if (flow.error() || ov.error()) { <p class="text-sm text-bad">{{ flow.error() || ov.error() }}</p> }
  @if (ov.data(); as o) {
    <div class="mb-6 grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-3 xl:grid-cols-6">
      <div><p class="stat-value">{{ o.open }}</p><p class="note mt-1">open tickets</p></div>
      <div><p class="stat-value">{{ num(o.cycle.p50) }}<span class="text-base text-muted"> d</span></p><p class="note mt-1">median cycle time</p></div>
      <div><p class="stat-value">{{ num(o.cycle.p85) }}<span class="text-base text-muted"> d</span></p><p class="note mt-1">85% finish within</p></div>
      <div><p class="stat-value">{{ num(o.throughput_avg) }}</p><p class="note mt-1">tickets done / week</p></div>
      <div><p class="stat-value text-accent">{{ o.forecast_p85 ? longDate(o.forecast_p85) : '—' }}</p><p class="note mt-1">all open work done (85%)</p></div>
      @if (o.high_risk !== null) {
        <div><p class="stat-value" [class.text-bad]="o.high_risk > 0">{{ o.high_risk }}</p><p class="note mt-1">high slip-risk tickets</p></div>
      }
    </div>
  }
  @if (flow.data(); as f) {
    @if (!f.available) {
      <p class="note">{{ f.reason }} Finish some tickets (or import history) to see flow metrics.</p>
    } @else {
      <div class="grid gap-5 xl:grid-cols-2">
        <section class="card">
          <h3 class="section-title">Cycle time</h3>
          <p class="note">Each dot is a finished ticket. Lines show the 50th, 85th and 95th percentiles: use the 85th when someone asks "when will it be done?"</p>
          <app-chart class="mt-3 h-72" [options]="scatter()" ariaLabel="Cycle time scatter plot" />
        </section>
        <section class="card">
          <h3 class="section-title">Weekly throughput</h3>
          <p class="note">Tickets finished per week. The forecast resamples the last 12 complete weeks.</p>
          <app-chart class="mt-3 h-72" [options]="throughput()" ariaLabel="Weekly throughput bar chart" />
        </section>
        <section class="card xl:col-span-2">
          <h3 class="section-title">Cumulative flow</h3>
          <p class="note">Tickets in each status over the last 120 days. A widening in-progress or blocked band means work is piling up.</p>
          <app-chart class="mt-3 h-72" [options]="cfd()" ariaLabel="Cumulative flow diagram" />
        </section>
      </div>

      <section class="card mt-5">
        <div class="flex flex-wrap items-center gap-3">
          <h3 class="section-title mr-auto">Where time goes</h3>
          <div class="flex gap-1 rounded-lg bg-canvas p-1 ring-1 ring-line" role="tablist">
            @for (t of groupings(); track t[0]) {
              <button role="tab" [attr.aria-selected]="group() === t[0]" (click)="group.set(t[0])"
                      class="rounded-md px-3 py-1 text-sm" [class.bg-raised]="group() === t[0]" [class.text-muted]="group() !== t[0]">{{ t[1] }}</button>
            }
          </div>
        </div>
        <div class="mt-4 overflow-x-auto">
          <table class="table">
            <thead><tr><th>{{ groupLabel() }}</th><th>Open</th><th>Done</th><th>Median cycle</th><th>85th pct</th><th>Finished late</th></tr></thead>
            <tbody>
              @for (r of rows(); track r.key) {
                <tr>
                  <td class="font-medium">{{ group() === 'kind' ? (kindLabel[r.key] ?? r.key) : r.key }}</td>
                  <td>{{ r.open }}</td><td>{{ r.done }}</td>
                  <td>{{ num(r.median_cycle_days) }} d</td><td>{{ num(r.p85_cycle_days) }} d</td>
                  <td [class.text-bad]="(r.slip_rate ?? 0) >= .5">{{ pct(r.slip_rate) }}</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </section>

      @if (f.aging.length) {
        <section class="card mt-5">
          <h3 class="section-title">Aging work in progress</h3>
          <p class="note">Active tickets by age. Red ones are older than 85% of tickets your team has finished: they're unlikely to close soon without help.</p>
          <ul class="mt-3 divide-y divide-line/60">
            @for (a of f.aging; track a.id) {
              <li class="flex items-center gap-3 py-2 text-sm">
                <span class="w-14 shrink-0 font-display text-lg" [class.text-bad]="a.over_p85">{{ a.age_days.toFixed(0) }}d</span>
                <span class="min-w-0 flex-1 truncate">{{ a.title }}</span>
                <span class="text-muted">{{ a.owner || 'Unassigned' }}</span>
                <span class="pill" [ngClass]="a.status === 'blocked' ? 'bg-bad/15 text-bad' : 'bg-info/15 text-info'">{{ a.status === 'blocked' ? 'Blocked' : 'In progress' }}</span>
              </li>
            }
          </ul>
        </section>
      }
    }
  } @else if (!flow.error()) { <p class="note">Crunching the numbers…</p> }`,
})
export class DeliveryView {
  private api = inject(Api);
  private ctx = inject(ProjectContext);
  readonly busy = signal(false);
  readonly exportError = signal('');

  async download(path: string, name: string) {
    this.busy.set(true);
    this.exportError.set('');
    try { await this.api.download(`/projects/${this.ctx.id()}/${path}`, name); }
    catch (e) { this.exportError.set(errorMessage(e)); }
    finally { this.busy.set(false); }
  }

  readonly flow = projectResource<Flow>((id) => `/projects/${id}/analytics/flow`);
  readonly ov = projectResource<Overview>((id) => `/projects/${id}/analytics/overview`);
  readonly kindLabel = KIND_LABEL;
  readonly num = num; readonly pct = pct; readonly longDate = longDate;
  readonly groupings = computed(() => {
    const all = [['kind', 'Type'], ['topic', 'Theme'], ['owner', 'Owner']] as const;
    return all.filter(([k]) => k !== 'topic' || (this.flow.data()?.by_topic.length ?? 0) > 0);
  });
  readonly group = signal<'kind' | 'topic' | 'owner'>('kind');
  readonly groupLabel = computed(() => ({ kind: 'Type', topic: 'Theme', owner: 'Owner' })[this.group()]);
  readonly rows = computed(() => {
    const f = this.flow.data();
    if (!f) return [];
    return { kind: f.by_kind, topic: f.by_topic, owner: f.by_owner }[this.group()];
  });

  readonly scatter = computed(() => {
    const f = this.flow.data();
    if (!f) return {};
    const kinds = [...new Set(f.cycle_time.points.map((p) => p.kind))];
    const p = f.cycle_time.percentiles;
    const line = (v: number, name: string, color: string) => ({ yAxis: v, name, lineStyle: { color, type: 'dashed' }, label: { color, formatter: `${name} ${v}d`, position: 'insideEndTop' } });
    return baseOption({
      tooltip: { trigger: 'item', backgroundColor: '#1B2235', borderColor: '#262E42', textStyle: { color: '#E5E9F2', fontSize: 12 },
        formatter: (x: { data: [string, number, string] }) => `${x.data[2]}<br/>${x.data[1]} days` },
      xAxis: { type: 'time', axisLine: { lineStyle: { color: '#262E42' } }, axisLabel: { color: '#8E98AE', fontSize: 11 }, splitLine: { show: false } },
      yAxis: { type: 'value', name: 'days', axisLabel: { color: '#8E98AE', fontSize: 11 }, splitLine: { lineStyle: { color: '#1F2638' } }, nameTextStyle: { color: '#8E98AE' } },
      series: kinds.map((k, i) => ({
        name: KIND_LABEL[k] ?? k, type: 'scatter', symbolSize: 6, itemStyle: { opacity: 0.75 },
        data: f.cycle_time.points.filter((pt) => pt.kind === k).map((pt) => [pt.date, pt.days, pt.title]),
        ...(i === 0 ? { markLine: { symbol: 'none', silent: true, data: [line(p.p50, '50%', '#52B5AA'), line(p.p85, '85%', '#F2B632'), line(p.p95, '95%', '#E66C63')] } } : {}),
      })),
    });
  });

  readonly throughput = computed(() => {
    const f = this.flow.data();
    if (!f) return {};
    return baseOption({
      xAxis: { type: 'category', data: f.throughput.weeks.map((w) => w.slice(5)), axisLabel: { color: '#8E98AE', fontSize: 11 }, axisLine: { lineStyle: { color: '#262E42' } } },
      yAxis: { type: 'value', axisLabel: { color: '#8E98AE' }, splitLine: { lineStyle: { color: '#1F2638' } } },
      series: [{ type: 'bar', name: 'Done', data: f.throughput.counts, itemStyle: { color: PALETTE[1], borderRadius: [3, 3, 0, 0] } }],
    });
  });

  readonly cfd = computed(() => {
    const f = this.flow.data();
    if (!f) return {};
    const order: [string, string, string][] = [['done', 'Done', '#52B5AA'], ['blocked', 'Blocked', '#E66C63'], ['in_progress', 'In progress', '#7D96F2'], ['planned', 'Planned', '#8E98AE']];
    return baseOption({
      xAxis: { type: 'category', boundaryGap: false, data: f.cfd.dates.map((d) => d.slice(5)), axisLabel: { color: '#8E98AE', fontSize: 11 }, axisLine: { lineStyle: { color: '#262E42' } } },
      yAxis: { type: 'value', axisLabel: { color: '#8E98AE' }, splitLine: { lineStyle: { color: '#1F2638' } } },
      series: order.map(([k, name, color]) => ({
        name, type: 'line', stack: 'flow', symbol: 'none', smooth: false, data: f.cfd.series[k],
        lineStyle: { width: 0 }, areaStyle: { color, opacity: k === 'done' ? 0.35 : 0.85 }, itemStyle: { color },
      })),
    });
  });
}
