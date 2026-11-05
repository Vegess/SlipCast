import { Component, DestroyRef, ElementRef, afterNextRender, effect, inject, input } from '@angular/core';
// Tree-shaken ECharts: only the chart types and components SlipCast uses are bundled.
import { BarChart, HeatmapChart, LineChart, ScatterChart } from 'echarts/charts';
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent, VisualMapComponent } from 'echarts/components';
import * as echarts from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([BarChart, HeatmapChart, LineChart, ScatterChart, GridComponent, LegendComponent, MarkLineComponent,
  TooltipComponent, VisualMapComponent, CanvasRenderer]);

export const PALETTE = ['#7D96F2', '#52B5AA', '#F2B632', '#B58CF0', '#E66C63', '#5DB0E8'];

/** Matches the Tailwind dark theme (canvas, panel, line, muted and fg colours). */
const THEME = {
  color: PALETTE,
  backgroundColor: 'transparent',
  textStyle: { color: '#E5E9F2', fontFamily: 'Instrument Sans, system-ui, sans-serif' },
  legend: { textStyle: { color: '#8E98AE' } },
};
echarts.registerTheme('slipcast-dark', THEME);

/** Shared defaults for every chart: compact grid, dark tooltip, legend only when asked. */
export function baseOption(option: Record<string, unknown>): Record<string, unknown> {
  return {
    animationDuration: 300,
    grid: { left: 44, right: 16, top: 24, bottom: 28, containLabel: false },
    tooltip: { trigger: 'axis', backgroundColor: '#1B2235', borderColor: '#262E42', textStyle: { color: '#E5E9F2', fontSize: 12 } },
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
  private chart: echarts.ECharts | null = null;

  constructor() {
    const destroyRef = inject(DestroyRef);
    afterNextRender(() => {
      this.chart = echarts.init(this.el.nativeElement, 'slipcast-dark', { renderer: 'canvas' });
      this.chart.setOption(this.options(), true);
      const ro = new ResizeObserver(() => this.chart?.resize());
      ro.observe(this.el.nativeElement);
      destroyRef.onDestroy(() => { ro.disconnect(); this.chart?.dispose(); this.chart = null; });
    });
    effect(() => {
      const opts = this.options();
      this.chart?.setOption(opts, true);
    });
  }
}
