import { Component, computed, input } from '@angular/core';
import { KIND_LABEL } from '../core/models';

/** Colour per ticket type: bug coral, feature blue, tech debt violet, support mint. */
export const KIND_STYLE: Partial<Record<string, { chip: string; dot: string }>> = {
  bug: { chip: 'bg-bad/15 text-bad-strong', dot: 'bg-bad' },
  feature: { chip: 'bg-info/15 text-info-strong', dot: 'bg-info' },
  tech_debt: { chip: 'bg-violet/15 text-violet-strong', dot: 'bg-violet' },
  support: { chip: 'bg-ok/15 text-ok-strong', dot: 'bg-ok' },
};
const NEUTRAL = { chip: 'bg-raised text-muted', dot: 'bg-muted' };

@Component({
  selector: 'app-kind-chip',
  template: `<span class="pill gap-1.5" [class]="style().chip"><span class="h-1.5 w-1.5 rounded-full" [class]="style().dot" aria-hidden="true"></span>{{ label() }}</span>`,
})
export class KindChip {
  readonly kind = input.required<string | null>();
  readonly style = computed(() => KIND_STYLE[this.kind() ?? ''] ?? NEUTRAL);
  readonly label = computed(() => KIND_LABEL[this.kind() ?? 'unknown'] ?? this.kind());
}
