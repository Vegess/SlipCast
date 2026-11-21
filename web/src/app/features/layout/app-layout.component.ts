import { AlertBell, Toaster } from '../../shared/alert-bell.component';
import { Component, OnInit, inject, signal } from '@angular/core';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';
import { AuthService } from '../../core/auth.service';

/**
 * Frame for every page except sign-in: the top navigation bar for signed-in users, or a
 * slim public header for visitors. Pages scroll inside; the projects area brings its own
 * sidebar and scroll container.
 */
@Component({
  selector: 'app-layout',
  imports: [AlertBell, Toaster, RouterOutlet, RouterLink, RouterLinkActive],
  template: `
  <div class="flex h-full flex-col">
    <header class="site-header relative z-40 shrink-0 border-b border-line bg-panel/95 backdrop-blur">
      <div class="flex h-14 items-center gap-2 px-4 sm:px-6">
        <a [routerLink]="auth.user() ? '/dashboard' : '/'" class="mr-4 flex items-center gap-2.5">
          <img src="favicon.svg" alt="" width="26" height="26">
          <span class="font-display text-lg font-bold">SlipCast</span>
        </a>

        @if (auth.user()) {
          <nav aria-label="Main" class="hidden items-center gap-1 md:flex">
            @for (l of links; track l.path) {
              <a [routerLink]="l.path" routerLinkActive="!bg-raised !text-fg" ariaCurrentWhenActive="page"
                 class="rounded-lg px-3 py-1.5 text-sm font-medium text-muted hover:bg-raised/60 hover:text-fg">{{ l.label }}</a>
            }
          </nav>
          <div class="ml-auto hidden items-center gap-3 md:flex">
            <app-alert-bell />
            <span class="max-w-[180px] truncate text-sm text-muted">{{ auth.user()?.name }}</span>
            <button class="btn btn-ghost px-2.5 py-1.5 text-sm" (click)="auth.logout()">Sign out</button>
          </div>
          <div class="ml-auto md:hidden"><app-alert-bell /></div>
          <button class="btn btn-ghost px-2.5 md:hidden" (click)="menu.set(!menu())"
                  [attr.aria-expanded]="menu()" aria-controls="mobile-menu" aria-label="Menu">
            <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true" class="stroke-fg" stroke-width="1.8" stroke-linecap="round">
              @if (menu()) { <path d="M5 5l10 10M15 5L5 15"/> } @else { <path d="M3 6h14M3 10h14M3 14h14"/> }
            </svg>
          </button>
        } @else {
          <nav aria-label="Main" class="ml-auto flex items-center gap-1 sm:gap-2">
            <a routerLink="/about" routerLinkActive="!text-fg" class="hidden rounded-lg px-3 py-1.5 text-sm font-medium text-muted hover:text-fg sm:inline">How it works</a>
            <a routerLink="/login" class="btn btn-ghost px-3 py-1.5">Sign in</a>
            <a routerLink="/login" [queryParams]="{ demo: 1 }" class="btn btn-primary px-3 py-1.5">Try the demo</a>
          </nav>
        }
      </div>

      @if (auth.user() && menu()) {
        <nav id="mobile-menu" aria-label="Main" class="grid gap-1 border-t border-line px-3 py-3 md:hidden">
          @for (l of links; track l.path) {
            <a [routerLink]="l.path" routerLinkActive="!bg-raised !text-fg" ariaCurrentWhenActive="page"
               class="rounded-lg px-3 py-2 text-sm font-medium text-muted">{{ l.label }}</a>
          }
          <div class="mt-1 flex items-center justify-between border-t border-line px-3 pt-3">
            <span class="truncate text-sm text-muted">{{ auth.user()?.name }}</span>
            <button class="btn btn-ghost px-2.5 py-1.5 text-sm" (click)="auth.logout()">Sign out</button>
          </div>
        </nav>
      }
    </header>
    <div class="min-h-0 flex-1 overflow-y-auto"><router-outlet /></div>
    @if (auth.user()) { <app-toaster /> }
  </div>`,
})
export class AppLayoutComponent implements OnInit {
  readonly auth = inject(AuthService);
  private router = inject(Router);
  readonly menu = signal(false);
  readonly links = [
    { path: '/dashboard', label: 'Dashboard' },
    { path: '/projects', label: 'Projects' },
    { path: '/imports', label: 'Imports' },
    { path: '/settings', label: 'Settings' },
    { path: '/about', label: 'About' },
  ];

  constructor() {
    // Close the mobile menu after navigating.
    this.router.events.pipe(filter((e) => e instanceof NavigationEnd)).subscribe(() => this.menu.set(false));
  }

  ngOnInit() { this.auth.ensureLoaded(); }
}
