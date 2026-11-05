import { Component, inject } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from '../../core/auth.service';

@Component({
  selector: 'app-not-found',
  imports: [RouterLink],
  template: `
  <div class="mx-auto flex max-w-xl flex-col items-start px-6 py-20">
    <p class="font-display text-7xl font-bold text-accent">404</p>
    <h1 class="mt-4 text-3xl font-bold">This page slipped.</h1>
    <p class="mt-3 text-muted">
      There's nothing at <code class="rounded bg-raised px-1.5 py-0.5 text-sm text-fg">{{ path }}</code>.
      Unlike our forecasts, we can't give you an 85% date for when it will show up.
    </p>
    <div class="mt-8 flex flex-wrap gap-2">
      <a class="btn btn-primary" [routerLink]="auth.user() ? '/dashboard' : '/'">{{ auth.user() ? 'Go to your dashboard' : 'Go to the home page' }}</a>
      <a class="btn" routerLink="/about">How SlipCast works</a>
    </div>
  </div>`,
})
export class NotFoundPage {
  readonly auth = inject(AuthService);
  readonly path = inject(Router).url;
}
