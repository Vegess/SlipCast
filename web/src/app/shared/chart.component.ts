import { Component, DestroyRef, ElementRef, afterNextRender, effect, inject, input } from '@angular/core';
// Tree-shaken ECharts: only the chart types and components SlipCast uses are bundled.
import { BarChart, HeatmapChart, LineChart, ScatterChart } from 'echarts/charts';
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent, VisualMapComponent } from 'echarts/components';
import * as echarts from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { DUSK, LIGHT, ThemeService, toLight } from '../core/theme.service';
import { prefersReducedMotion } from './motion';

echarts.use([BarChart, HeatmapChart, LineChart, ScatterChart, GridComponent, LegendComponent, MarkLineComponent,
  TooltipComponent, VisualMapComponent, CanvasRenderer]);

export const PALETTE = [DUSK.info, DUSK.ok, DUSK.accent, DUSK.violet, DUSK.bad, DUSK.sky];

/** One ECharts theme per app theme; option colours are written in Dusk and remapped for light. */
for (const [name, c] of [['dusk', DUSK], ['light', LIGHT]] as const) {
  echarts.registerTheme(`slipcast-${name}`, {
    color: [c.info, c.ok, c.accent, c.violet, c.bad, c.sky],
    backgroundColor: 'transparent',
    textStyle: { color: c.fg, fontFamily: 'Instrument Sans, system-ui, sans-serif' },
    legend: { textStyle: { color: c.muted } },
  });
}

/**
 * Entry animation for charts: bars grow one after another, lines draw left to right, and
 * points settle in. Updates (new data, theme switch) glide instead of redrawing. Off when the
 * person prefers reduced motion.
 */
export function chartMotion(): Record<string, unknown> {
  if (prefersReducedMotion()) return { animation: false };
  return {
    animation: true,
    animationDuration: 950,
    animationEasing: 'cubicOut',
    animationDelay: (idx: number) => Math.min(idx * 16, 520),
    animationDurationUpdate: 450,
    animationEasingUpdate: 'cubicInOut',
  };
}

/** Shared defaults for every chart: compact grid, dark tooltip, legend only when asked. */
export function baseOption(option: Record<string, unknown>): Record<string, unknown> {
  return {
    ...chartMotion(),
    grid: { left: 44, right: 16, top: 24, bottom: 28, containLabel: false },
    tooltip: { trigger: 'axis', backgroundColor: '#28354F', borderColor: '#34425E', textStyle: { color: '#EEF2F8', fontSize: 12 } },
    ...option,
  };
}

@Component({
  selector: 'app-chart',
  host: { class: 'block', role: 'img', '[attr.aria-label]': 'ariaLabel()' },
  template: '',
})
export class ChartComponent {
  readonly options = input.required<Record<string, unknown>>();
  readonly ariaLabel = input('');
  private el = inject(ElementRef<HTMLElement>);
  private theme = inject(ThemeService).theme;
  private chart: echarts.ECharts | null = null;
  private rendered = false;

  constructor() {
    const destroyRef = inject(DestroyRef);
    afterNextRender(() => {
      this.rendered = true;
      this.draw();
      const ro = new ResizeObserver(() => this.chart?.resize());
      ro.observe(this.el.nativeElement);
      destroyRef.onDestroy(() => { ro.disconnect(); this.chart?.dispose(); this.chart = null; });
    });
    effect(() => {
      this.options();
      this.theme();
      if (this.rendered) this.draw();
    });
  }

  private drawnTheme = '';
  private draw() {
    const theme = this.theme();
    if (this.chart && this.drawnTheme !== theme) { this.chart.dispose(); this.chart = null; }
    if (!this.chart) {
      this.chart = echarts.init(this.el.nativeElement, `slipcast-${theme}`, { renderer: 'canvas' });
      this.drawnTheme = theme;
    }
    const opts = { ...chartMotion(), ...this.options() };
    this.chart.setOption(theme === 'light' ? toLight(opts) : opts, true);
  }
}
