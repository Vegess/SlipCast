import { DestroyRef, Directive, ElementRef, afterNextRender, inject, input } from '@angular/core';

/** True when the person has asked their system for less motion. Checked once per call. */
export function prefersReducedMotion(): boolean {
  return typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/** Calls `onVisible` once when the element first scrolls into view (immediately without IntersectionObserver). */
function whenVisible(el: HTMLElement, destroyRef: DestroyRef, onVisible: () => void, threshold = 0.15): void {
  if (typeof IntersectionObserver === 'undefined') { onVisible(); return; }
  const io = new IntersectionObserver((entries) => {
    if (entries.some((e) => e.isIntersecting)) { io.disconnect(); onVisible(); }
  }, { threshold, rootMargin: '0px 0px -8% 0px' });
  io.observe(el);
  destroyRef.onDestroy(() => io.disconnect());
}

/**
 * Fades and lifts an element in the first time it scrolls into view.
 * `appReveal` takes an optional step number; each step waits a little longer, for a stagger.
 */
@Directive({
  selector: '[appReveal]',
  host: { class: 'reveal', '[style.--i]': 'step()' },
})
export class RevealDirective {
  readonly step = input(0, { alias: 'appReveal', transform: (v: unknown) => Number(v) || 0 });

  constructor() {
    const el = inject(ElementRef<HTMLElement>).nativeElement;
    const destroyRef = inject(DestroyRef);
    afterNextRender(() => whenVisible(el, destroyRef, () => el.classList.add('is-visible')));
  }
}

/**
 * Counts a number up from zero when it scrolls into view, e.g. `<span [appCountUp]="92" suffix="%">`.
 * The final value is in the DOM from the start, so screen readers and reduced motion see it as is.
 */
@Directive({ selector: '[appCountUp]' })
export class CountUpDirective {
  readonly value = input.required<number>({ alias: 'appCountUp' });
  readonly suffix = input('');
  readonly decimals = input(0);
  readonly duration = input(1100);

  constructor() {
    const el = inject(ElementRef<HTMLElement>).nativeElement;
    const destroyRef = inject(DestroyRef);
    let frame = 0;
    destroyRef.onDestroy(() => cancelAnimationFrame(frame));
    afterNextRender(() => {
      const text = (n: number) => `${n.toFixed(this.decimals())}${this.suffix()}`;
      el.textContent = text(this.value());
      if (prefersReducedMotion()) return;
      el.textContent = text(0);
      whenVisible(el, destroyRef, () => {
        const start = performance.now();
        const tick = (now: number) => {
          const t = Math.min(1, (now - start) / this.duration());
          const eased = 1 - Math.pow(1 - t, 3); // ease-out cubic: quick start, gentle landing
          el.textContent = text(this.value() * eased);
          if (t < 1) frame = requestAnimationFrame(tick);
        };
        frame = requestAnimationFrame(tick);
      }, 0.4);
    });
  }
}
