import { Component } from '@angular/core';
import { RevealDirective } from './motion';

/**
 * Landing page: how SlipCast reads a ticket, in four small animated drawings that play in
 * order when scrolled into view. Every element's resting state is the final picture and the
 * animations only run *from* a hidden state, so reduced motion simply shows the finished drawing.
 */
@Component({
  selector: 'app-story-diagram',
  imports: [RevealDirective],
  styles: [`
    .step { --d: calc(var(--s) * 0.9s); }
    .is-visible .draw { animation: draw 0.9s cubic-bezier(.6,0,.3,1) var(--d) backwards; }
    .is-visible .pop { animation: pop 0.45s cubic-bezier(.2,.8,.2,1) calc(var(--d) + var(--k, 0) * 70ms + 0.2s) backwards; }
    .is-visible .dim { animation: dim 0.6s ease-out calc(var(--d) + 0.5s) backwards; }
    .is-visible .grow { animation: grow 0.9s cubic-bezier(.2,.8,.2,1) calc(var(--d) + 0.3s) backwards; }
    .is-visible .fade { animation: fade 0.5s ease-out calc(var(--d) + var(--k, 0) * 120ms + 0.5s) backwards; }
    .is-visible .ring { animation: ring 1.2s cubic-bezier(.3,.7,.2,1) calc(var(--d) + 0.2s) backwards; }
    .caret { animation: blink 1s steps(2) infinite; }
    .grow { transform-box: fill-box; transform-origin: left center; }
    .pop { transform-box: fill-box; transform-origin: center; }
    @keyframes draw { from { stroke-dashoffset: var(--len); } }
    @keyframes pop { from { opacity: 0; transform: scale(0.2); } }
    @keyframes dim { from { opacity: 1; } }
    @keyframes grow { from { transform: scaleX(0); } }
    @keyframes fade { from { opacity: 0; transform: translateY(4px); } }
    @keyframes ring { from { stroke-dashoffset: 276; } }
    @keyframes blink { 50% { opacity: 0; } }
  `],
  template: `
  <div appReveal class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
    <!-- 1. A ticket is written -->
    <figure class="step card p-4" style="--s: 0">
      <svg viewBox="0 0 200 130" class="w-full" aria-hidden="true">
        <rect x="18" y="12" width="164" height="106" rx="12" class="fill-canvas stroke-line" stroke-width="1.5"/>
        <rect x="18" y="12" width="164" height="22" rx="12" class="fill-raised"/>
        <circle cx="32" cy="23" r="3.5" class="fill-accent"/>
        <text x="42" y="27" class="fill-muted text-[10px]">New ticket</text>
        <path class="draw stroke-fg" style="--len: 120" stroke-dasharray="120" d="M32 52 H152" stroke-width="5" stroke-linecap="round"/>
        <path class="draw stroke-muted/60" style="--len: 130; animation-delay: calc(var(--d) + .35s)" stroke-dasharray="130" d="M32 72 H162" stroke-width="3.5" stroke-linecap="round"/>
        <path class="draw stroke-muted/60" style="--len: 90; animation-delay: calc(var(--d) + .6s)" stroke-dasharray="90" d="M32 88 H122" stroke-width="3.5" stroke-linecap="round"/>
        <rect x="126" y="82" width="2" height="12" class="caret fill-accent"/>
        <text x="32" y="109" class="fade fill-accent text-[10px] font-semibold" style="--k: 4">Due in 3 days</text>
      </svg>
      <figcaption class="mt-3 text-sm"><b class="block text-fg">1. You write a ticket.</b> <span class="text-muted">The check starts while you type.</span></figcaption>
    </figure>

    <!-- 2. Similar finished tickets are found -->
    <figure class="step card p-4" style="--s: 1">
      <svg viewBox="0 0 200 130" class="w-full" aria-hidden="true">
        @for (d of crowd; track $index) {
          <circle [attr.cx]="d[0]" [attr.cy]="d[1]" r="5" class="dim fill-muted" opacity=".3"/>
        }
        @for (m of matches; track $index; let k = $index) {
          <path class="draw stroke-info/50" [style.--len]="m[2]" [attr.stroke-dasharray]="m[2]"
                [attr.d]="'M100 65 L' + m[0] + ' ' + m[1]" stroke-width="1.5" [style.animation-delay]="'calc(var(--d) + ' + (0.25 + k * 0.07) + 's)'"/>
          <circle [attr.cx]="m[0]" [attr.cy]="m[1]" r="6" class="pop fill-info" [style.--k]="k"/>
        }
        <circle cx="100" cy="65" r="9" class="pop fill-accent" style="--k: 0"/>
      </svg>
      <figcaption class="mt-3 text-sm"><b class="block text-fg">2. It finds tickets like it.</b> <span class="text-muted">The most similar finished ones, by their words.</span></figcaption>
    </figure>

    <!-- 3. How long they really took -->
    <figure class="step card p-4" style="--s: 2">
      <svg viewBox="0 0 200 130" class="w-full" aria-hidden="true">
        <path d="M16 92 H186" class="stroke-line" stroke-width="1.5"/>
        @for (t of ticks; track t) {
          <path [attr.d]="'M' + x(t) + ' 92 v5'" class="stroke-line" stroke-width="1.5"/>
          <text [attr.x]="x(t)" y="110" text-anchor="middle" class="fill-muted text-[9px]">{{ t }}</text>
        }
        <text x="186" y="122" text-anchor="end" class="fill-muted text-[8px]">days</text>
        <rect [attr.x]="x(4)" y="58" [attr.width]="x(11) - x(4)" height="22" rx="6" class="grow fill-info/30 stroke-info" stroke-width="1.5"/>
        <path [attr.d]="'M' + x(6.5) + ' 54 V84'" class="fade stroke-info" stroke-width="2.5" stroke-linecap="round" style="--k: 2"/>
        <text [attr.x]="(x(4) + x(11)) / 2" y="47" text-anchor="middle" class="fade fill-fg text-[11px] font-semibold" style="--k: 3">took 4–11 days</text>
        <path [attr.d]="'M' + x(3) + ' 30 V92'" class="fade stroke-bad" stroke-width="2" stroke-dasharray="3 3" style="--k: 5"/>
        <text [attr.x]="x(3) - 4" y="25" text-anchor="end" class="fade fill-bad text-[10px] font-semibold" style="--k: 6">you planned 3</text>
      </svg>
      <figcaption class="mt-3 text-sm"><b class="block text-fg">3. It shows what really happened.</b> <span class="text-muted">A range from history, not a guess.</span></figcaption>
    </figure>

    <!-- 4. It scores itself -->
    <figure class="step card p-4" style="--s: 3">
      <svg viewBox="0 0 200 130" class="w-full" aria-hidden="true">
        <circle cx="100" cy="62" r="44" class="fill-none stroke-raised" stroke-width="10"/>
        <circle cx="100" cy="62" r="44" class="ring fill-none stroke-ok" stroke-width="10" stroke-linecap="round"
                stroke-dasharray="276" stroke-dashoffset="47" transform="rotate(-90 100 62)"/>
        <text x="100" y="60" text-anchor="middle" class="fade fill-fg text-[22px] font-bold" style="--k: 3">83%</text>
        <text x="100" y="77" text-anchor="middle" class="fade fill-muted text-[9px]" style="--k: 4">came true</text>
        <path class="draw stroke-ok" style="--len: 30; animation-delay: calc(var(--d) + 1.2s)" stroke-dasharray="30"
              d="M150 104 l7 7 l14 -16" fill="none" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <figcaption class="mt-3 text-sm"><b class="block text-fg">4. Then it checks itself.</b> <span class="text-muted">Every forecast is scored when the work finishes.</span></figcaption>
    </figure>
  </div>`,
})
export class StoryDiagram {
  readonly ticks = [0, 5, 10, 15];
  /** Days → x position on the small timeline. */
  x(days: number) { return 22 + (days / 15) * 158; }
  readonly crowd = [[24, 20], [58, 108], [170, 112], [182, 30], [30, 76], [140, 10], [76, 16], [118, 118], [186, 72], [14, 116]];
  /** [x, y, line length] for the matches that light up */
  readonly matches = [[46, 40, 60], [150, 46, 54], [62, 92, 46], [140, 90, 47], [100, 22, 43], [122, 64, 22]];
}
