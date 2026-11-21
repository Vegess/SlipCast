import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { errorMessage } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';

const METHOD_LABEL: Record<string, string | undefined> = { password: 'Email and password', google: 'Google', github: 'GitHub' };

@Component({
  selector: 'app-account-settings',
  imports: [FormsModule],
  template: `
  <section class="card card-info anim-rise">
    <h2 class="section-title">How you sign in</h2>
    <p class="note mt-1">Any of these opens the same account, {{ auth.user()?.email }}.</p>
    <ul class="mt-4 flex flex-wrap gap-2">
      @for (m of auth.signInMethods(); track m) {
        <li class="pill gap-1.5 bg-ok/15 text-ok-strong"><span aria-hidden="true">✓</span>{{ label[m] ?? m }}</li>
      }
    </ul>
    <p class="note mt-3">To add Google or GitHub, sign out and use "Continue with…" with a verified account that has this same email address.</p>
  </section>

  <section class="card card-violet anim-rise mt-5" style="--i: 1">
    <h2 class="section-title">{{ auth.hasPassword() ? 'Change password' : 'Set a password' }}</h2>
    <p class="note mt-1">
      @if (auth.hasPassword()) { Changing it signs you out on every other device. }
      @else { You sign in with {{ providerNames() }}. A password lets you sign in with your email too. }
    </p>
    <form class="mt-4 grid gap-4 sm:max-w-sm" (ngSubmit)="savePassword()">
      @if (auth.hasPassword()) {
        <label class="label">Current password <input class="input" type="password" name="current" [(ngModel)]="current" required autocomplete="current-password"></label>
      }
      <label class="label">New password
        <input class="input" type="password" name="next" [(ngModel)]="next" required minlength="8" maxlength="64" autocomplete="new-password">
        <span class="font-normal">At least 8 characters.</span>
      </label>
      <button class="btn btn-primary justify-self-start" [disabled]="busy() || next.length < 8 || (auth.hasPassword() && !current)">
        {{ busy() ? 'Saving…' : auth.hasPassword() ? 'Change password' : 'Set password' }}</button>
    </form>
    @if (saved()) { <p class="mt-3 text-sm text-ok" role="status">Password saved. Other devices have been signed out.</p> }
    @if (error()) { <p class="mt-3 text-sm text-bad" role="alert">{{ error() }}</p> }
  </section>

  <section class="card card-accent anim-rise mt-5" style="--i: 2">
    <h2 class="section-title">Sign out everywhere</h2>
    <p class="note mt-1">Ends every session on every device, including this one. Use it if you signed in on a computer you don't own.</p>
    <button class="btn mt-4" (click)="logoutEverywhere()" [disabled]="busy()">Sign out everywhere</button>
  </section>`,
})
export class AccountSettings {
  readonly auth = inject(AuthService);
  readonly label = METHOD_LABEL;
  readonly busy = signal(false);
  readonly saved = signal(false);
  readonly error = signal('');
  current = ''; next = '';

  providerNames() {
    return this.auth.signInMethods().filter((m) => m !== 'password').map((m) => METHOD_LABEL[m] ?? m).join(' and ');
  }

  async savePassword() {
    this.busy.set(true); this.saved.set(false); this.error.set('');
    try {
      await this.auth.changePassword(this.current, this.next);
      this.current = ''; this.next = ''; this.saved.set(true);
    } catch (e) { this.error.set(errorMessage(e)); }
    finally { this.busy.set(false); }
  }

  async logoutEverywhere() {
    if (!confirm('Sign out on every device, including this one?')) return;
    this.busy.set(true);
    try { await this.auth.logoutEverywhere(); } catch (e) { this.error.set(errorMessage(e)); this.busy.set(false); }
  }
}
