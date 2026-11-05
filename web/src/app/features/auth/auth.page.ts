import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { errorMessage } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';

@Component({
  selector: 'app-auth-page',
  imports: [FormsModule],
  template: `
  <div class="grid min-h-full lg:grid-cols-[1.25fr_1fr]">
    <section class="flex flex-col justify-between px-6 py-8 sm:px-12 lg:border-r lg:border-line lg:py-14">
      <span class="font-display text-xl font-bold">SlipCast</span>
      <div class="my-10 max-w-xl">
        <h1 class="text-4xl font-bold leading-[1.05] sm:text-6xl">Know when your work will really ship, and why it slips.</h1>
        <p class="mt-5 max-w-md text-base text-muted">
          SlipCast turns your ticket history from Jira, GitHub or Trello into a clear picture of how
          work actually flows through your team, and where it gets stuck.
        </p>
        <svg viewBox="0 0 520 220" class="mt-10 hidden w-full max-w-lg sm:block" aria-hidden="true">
          <path d="M0 200 L60 182 L120 170 L180 150 L240 138 L300 112 L360 96" fill="none" stroke="#E5E9F2" stroke-width="3" stroke-linecap="round"/>
          <path d="M360 96 L420 70 L480 52 L520 40 L520 92 L480 96 L420 104 L360 96 Z" fill="#F2B632" fill-opacity=".14"/>
          <path d="M360 96 L420 84 L480 72 L520 64" fill="none" stroke="#F2B632" stroke-width="2.5" stroke-dasharray="6 6"/>
          @for (p of pins; track $index) {
            <circle [attr.cx]="p[0]" [attr.cy]="p[1]" r="6" fill="#0D1220" [attr.stroke]="p[2]" stroke-width="2.5"/>
          }
          
        </svg>
      </div>
      <p class="text-xs text-muted">Angular · FastAPI · PostgreSQL · pandas</p>
    </section>

    <section class="flex items-center justify-center px-6 py-10">
      <form class="w-full max-w-sm" (ngSubmit)="submit()">
        <h2 class="text-2xl font-medium">{{ mode() === 'signin' ? 'Sign in' : 'Create your account' }}</h2>
        <p class="mt-1 text-sm text-muted">{{ mode() === 'signin' ? 'Welcome back.' : 'You get a private workspace for your projects.' }}</p>
        <div class="mt-6 grid gap-4">
          @if (mode() === 'register') {
            <label class="label">Name <input class="input" name="name" [(ngModel)]="name" required maxlength="80" autocomplete="name"></label>
          }
          <label class="label">Email <input class="input" type="email" name="email" [(ngModel)]="email" required autocomplete="email"></label>
          <label class="label">Password
            <input class="input" type="password" name="password" [(ngModel)]="password" required maxlength="64"
                   [attr.minlength]="mode() === 'register' ? 8 : 1"
                   [attr.autocomplete]="mode() === 'signin' ? 'current-password' : 'new-password'">
            @if (mode() === 'register') { <span class="font-normal">At least 8 characters.</span> }
          </label>
          @if (error()) { <p class="text-sm text-bad">{{ error() }}</p> }
          <button class="btn btn-primary w-full py-2.5" [disabled]="busy()">
            {{ busy() ? 'One moment…' : mode() === 'signin' ? 'Sign in' : 'Create account' }}
          </button>
        </div>
        <p class="mt-6 text-sm text-muted">
          {{ mode() === 'signin' ? 'New to SlipCast?' : 'Already have an account?' }}
          <button type="button" class="font-medium text-info hover:underline" (click)="toggle()">
            {{ mode() === 'signin' ? 'Create an account' : 'Sign in' }}
          </button>
        </p>
      </form>
    </section>
  </div>`,
})
export class AuthPage {
  private auth = inject(AuthService);
  readonly mode = signal<'signin' | 'register'>('signin');
  readonly busy = signal(false);
  readonly error = signal('');
  name = ''; email = ''; password = '';
  readonly pins: [number, number, string][] = [[60, 182, '#52B5AA'], [180, 150, '#52B5AA'], [300, 112, '#7D96F2'], [360, 96, '#F2B632']];

  toggle() { this.mode.set(this.mode() === 'signin' ? 'register' : 'signin'); this.error.set(''); }

  async submit() {
    this.busy.set(true);
    this.error.set('');
    try {
      if (this.mode() === 'signin') await this.auth.login(this.email, this.password);
      else await this.auth.register(this.name, this.email, this.password);
    } catch (e) {
      this.error.set(errorMessage(e));
    } finally {
      this.busy.set(false);
    }
  }
}
