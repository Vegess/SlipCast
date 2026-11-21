import { Component, ElementRef, HostListener, effect, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { AlertsService } from '../core/alerts.service';

/** Top-bar bell: rings when an alert arrives; the menu lists the workspace's latest alerts. */
@Component({
  selector: 'app-alert-bell',
  imports: [RouterLink],
  template: `
  <div class="relative">
    <button class="btn btn-ghost relative px-2" (click)="toggle()" [attr.aria-expanded]="open()" aria-haspopup="true"
            [attr.aria-label]="alerts.unseen() ? alerts.unseen() + ' new alerts' : 'Alerts'">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true" class="bell stroke-fg" [class.ringing]="ringing()"
           stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <path d="M6 9a6 6 0 1 1 12 0c0 5 2 6.5 2 6.5H4S6 14 6 9Z"/>
        <path class="clapper" d="M10 19a2 2 0 0 0 4 0"/>
      </svg>
      @if (alerts.unseen()) {
        <span class="anim-pop absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-bad px-1 text-[10px] font-bold text-white">{{ alerts.unseen() > 9 ? '9+' : alerts.unseen() }}</span>
      }
    </button>
    @if (open()) {
      <div class="anim-pop absolute right-0 z-50 mt-2 w-[min(92vw,380px)] overflow-hidden rounded-xl border border-line bg-panel shadow-2xl" role="menu">
        <div class="flex items-center justify-between border-b border-line px-4 py-3">
          <p class="text-sm font-medium">Alerts</p>
          <span class="text-xs text-muted">Forecast moves and risky new work</span>
        </div>
        <ul class="max-h-[60vh] overflow-y-auto">
          @for (a of alerts.items(); track a.id; let i = $index) {
            <li class="anim-rise border-b border-line/60 last:border-0" [style.--i]="i < 8 ? i : 8">
              <a [routerLink]="['/projects', a.project_id, a.kind === 'high_risk' ? 'board' : 'forecast']" (click)="open.set(false)"
                 class="flex gap-3 px-4 py-3 hover:bg-raised/60" role="menuitem">
                <span class="mt-1.5 h-2 w-2 shrink-0 rounded-full" [class.bg-bad]="a.severity === 'critical'"
                      [class.bg-accent]="a.severity === 'warning'" [class.bg-info]="a.severity === 'info'" aria-hidden="true"></span>
                <span class="min-w-0">
                  <span class="block text-sm leading-snug">{{ a.message }}</span>
                  <span class="mt-0.5 block text-xs text-muted">{{ a.project_name }} · {{ ago(a.created_at) }}</span>
                </span>
              </a>
            </li>
          } @empty {
            <li class="px-4 py-8 text-center text-sm text-muted">No alerts yet. You'll hear here when a forecast moves by two days or more, or new work looks likely to slip.</li>
          }
        </ul>
      </div>
    }
  </div>`,
})
export class AlertBell {
  readonly alerts = inject(AlertsService);
  private el = inject(ElementRef<HTMLElement>);
  readonly open = signal(false);
  readonly ringing = signal(false);

  constructor() {
    let first = true;
    effect(() => {
      this.alerts.rings();
      if (first) { first = false; return; }
      this.ringing.set(false);
      requestAnimationFrame(() => this.ringing.set(true));
      setTimeout(() => this.ringing.set(false), 1200);
    });
  }

  toggle() {
    this.open.update((o) => !o);
    if (this.open()) this.alerts.markSeen();
  }

  @HostListener('document:click', ['$event'])
  outside(ev: MouseEvent) { if (this.open() && !this.el.nativeElement.contains(ev.target as Node)) this.open.set(false); }

  @HostListener('document:keydown.escape')
  esc() { this.open.set(false); }

  ago(iso: string): string {
    const s = (Date.now() - new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z').getTime()) / 1000;
    if (s < 60) return 'just now';
    if (s < 3600) return `${Math.round(s / 60)} min ago`;
    if (s < 86400) return `${Math.round(s / 3600)} h ago`;
    return `${Math.round(s / 86400)} d ago`;
  }
}

/** Live alerts slide in at the bottom right; each has a small animated icon. */
@Component({
  selector: 'app-toaster',
  imports: [RouterLink],
  template: `
  <div class="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[min(92vw,380px)] flex-col gap-2" aria-live="polite">
    @for (t of alerts.toasts(); track t.id) {
      <div class="toast pointer-events-auto flex gap-3 rounded-xl border border-line bg-panel p-3.5 shadow-2xl"
           [class.border-l-bad]="t.severity === 'critical'" [class.border-l-accent]="t.severity === 'warning'" [class.border-l-info]="t.severity === 'info'">
        <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true" class="shrink-0">
          <circle cx="14" cy="14" r="12" class="toast-ring" [class.stroke-bad]="t.severity === 'critical'"
                  [class.stroke-accent]="t.severity === 'warning'" [class.stroke-info]="t.severity === 'info'" stroke-width="2"/>
          @if (t.kind === 'forecast_slip' || t.kind === 'forecast_gain') {
            <path class="toast-mark stroke-fg" [attr.d]="t.kind === 'forecast_slip' ? 'M8 11l6 6 6-6' : 'M8 17l6-6 6 6'" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
          } @else {
            <path class="toast-mark stroke-fg" d="M14 8v7M14 19.5v.01" stroke-width="2.4" stroke-linecap="round"/>
          }
        </svg>
        <a class="min-w-0 flex-1 text-sm" [routerLink]="['/projects', t.project_id, t.kind === 'high_risk' ? 'board' : 'forecast']">
          <span class="block font-medium">{{ t.kind === 'high_risk' ? 'Likely to slip' : t.kind === 'forecast_gain' ? 'Forecast improved' : 'Forecast slipped' }}</span>
          <span class="block text-muted">{{ t.message }}</span>
        </a>
        <button class="self-start text-muted hover:text-fg" (click)="alerts.dismiss(t.id)" aria-label="Dismiss">✕</button>
      </div>
    }
  </div>`,
})
export class Toaster {
  readonly alerts = inject(AlertsService);
}
