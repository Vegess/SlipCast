import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { Api, errorMessage } from '../../core/api.service';
import { Project } from '../../core/models';
import { AuthService } from '../../core/auth.service';

@Component({
  selector: 'app-auth-page',
  imports: [FormsModule, RouterLink],
  template: `
  <div class="grid min-h-full lg:grid-cols-[1.25fr_1fr]">
    <section class="flex flex-col justify-between px-6 py-8 sm:px-12 lg:border-r lg:border-line lg:py-14">
      <a routerLink="/" class="font-display text-xl font-bold hover:text-accent">SlipCast</a>
      <div class="my-10 max-w-xl">
        <h1 class="anim-rise text-4xl font-bold leading-[1.05] sm:text-6xl">Know when your work will really ship, and why it slips.</h1>
        <p class="anim-rise mt-5 max-w-md text-base text-muted" style="--i: 3">
          SlipCast turns your ticket history from Jira, GitHub or Trello into a clear picture of how
          work actually flows through your team, and where it gets stuck.
        </p>
        <svg viewBox="0 0 520 220" class="mt-10 hidden w-full max-w-lg sm:block" aria-hidden="true">
          <!-- History draws itself, then the forecast cone opens and its dashed median keeps moving. -->
          <path d="M0 200 L60 182 L120 170 L180 150 L240 138 L300 112 L360 96" fill="none" class="draw-line stroke-fg" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M360 96 L420 70 L480 52 L520 40 L520 92 L480 96 L420 104 L360 96 Z" class="anim-fade fill-accent" fill-opacity=".14" style="animation-delay: 1.6s; animation-duration: 0.9s"/>
          <g class="anim-fade" style="animation-delay: 1.8s">
            <path d="M360 96 L420 84 L480 72 L520 64" fill="none" class="march stroke-accent" stroke-width="2.5" stroke-dasharray="6 6"/>
          </g>
          <circle cx="360" cy="96" r="6" class="ring-pulse fill-none stroke-accent" stroke-width="2" style="animation-delay: 2s; opacity: 0"/>
          @for (p of pins; track $index) {
            <circle [attr.cx]="p[0]" [attr.cy]="p[1]" r="6" [attr.class]="'anim-fade fill-canvas ' + p[2]" stroke-width="2.5"
                    [style.animation-delay]="(0.25 + p[0] / 360 * 1.35) + 's'"/>
          }
          
        </svg>
      </div>
      <p class="text-xs text-muted">Angular · FastAPI · PostgreSQL · pandas · scikit-learn</p>
    </section>

    <section class="flex items-center justify-center px-6 py-10">
      <form class="anim-rise w-full max-w-sm" style="--i: 2" (ngSubmit)="submit()">
        <h2 class="text-2xl font-medium">{{ mode() === 'signin' ? 'Sign in' : 'Create your account' }}</h2>
        <p class="mt-1 text-sm text-muted">{{ mode() === 'signin' ? 'Welcome back.' : demo() ? 'Create a free account and we will load six months of demo tickets for you.' : 'You get a private workspace for your projects.' }}</p>
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
            {{ busy() ? 'One moment…' : mode() === 'signin' ? 'Sign in' : demo() ? 'Create account and open the demo' : 'Create account' }}
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
export class AuthPage implements OnInit {
  private auth = inject(AuthService);
  private api = inject(Api);
  private router = inject(Router);
  private route = inject(ActivatedRoute);
  /** Came from "Try the demo": after signing up, open a fresh demo project. */
  readonly demo = signal(false);
  readonly mode = signal<'signin' | 'register'>('signin');
  readonly busy = signal(false);
  readonly error = signal('');
  name = ''; email = ''; password = '';
  readonly pins: [number, number, string][] = [[60, 182, 'stroke-ok'], [180, 150, 'stroke-ok'], [300, 112, 'stroke-info'], [360, 96, 'stroke-accent']];

  ngOnInit() {
    const q = this.route.snapshot.queryParamMap;
    this.demo.set(q.get('demo') === '1');
    if (q.get('mode') === 'register' || this.demo()) this.mode.set('register');
  }

  toggle() { this.mode.set(this.mode() === 'signin' ? 'register' : 'signin'); this.error.set(''); }

  async submit() {
    this.busy.set(true);
    this.error.set('');
    try {
      if (this.mode() === 'signin') await this.auth.login(this.email, this.password);
      else await this.auth.register(this.name, this.email, this.password);
      if (this.demo()) {
        const ws = this.auth.workspace()!.id;
        const p = await this.api.post<Project>(`/workspaces/${ws}/demo-project`);
        await this.router.navigate(['/projects', p.id, 'board']);
      } else {
        await this.router.navigateByUrl('/dashboard');
      }
    } catch (e) {
      this.error.set(errorMessage(e));
    } finally {
      this.busy.set(false);
    }
  }
}
