import { Component, ElementRef, HostListener, OnInit, input, output } from '@angular/core';

@Component({
  selector: 'app-modal',
  template: `
    <div class="anim-fade fixed inset-0 z-50 flex items-end justify-center bg-black/60 sm:items-center sm:p-6"
         (mousedown)="onBackdrop($event)">
      <div role="dialog" aria-modal="true" [attr.aria-label]="heading()"
           class="anim-pop flex max-h-[92dvh] w-full flex-col rounded-t-2xl border border-line bg-panel shadow-2xl sm:rounded-2xl"
           [class.sm:max-w-lg]="!wide()" [class.sm:max-w-3xl]="wide()">
        <div class="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 class="text-lg font-medium">{{ heading() }}</h2>
          <button class="btn btn-ghost px-2" (click)="closed.emit()" aria-label="Close">✕</button>
        </div>
        <div class="overflow-y-auto px-5 py-4"><ng-content /></div>
        <div class="flex flex-wrap items-center justify-end gap-2 border-t border-line px-5 py-3 empty:hidden">
          <ng-content select="[footer]" />
        </div>
      </div>
    </div>`,
})
export class ModalComponent implements OnInit {
  readonly heading = input.required<string>();
  readonly wide = input(false);
  readonly closed = output<void>();

  constructor(private el: ElementRef<HTMLElement>) {}

  ngOnInit() {
    setTimeout(() => this.el.nativeElement.querySelector<HTMLElement>('input, textarea, select')?.focus());
  }

  /**
   * Close only when the press starts on the backdrop itself. This must not be an inline
   * `a && b` template expression: when it evaluates to `false` Angular calls
   * preventDefault() on the mousedown, and inputs inside the dialog can no longer take focus.
   */
  onBackdrop(ev: MouseEvent): void {
    if (ev.target === ev.currentTarget) this.closed.emit();
  }

  @HostListener('document:keydown.escape')
  onEscape() { this.closed.emit(); }
}
