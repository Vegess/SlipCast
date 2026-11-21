import { Component, OnInit, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { errorMessage } from '../../core/api.service';
import { AuthService, safeNext } from '../../core/auth.service';

/**
 * Google/GitHub sign-in ends here. The API puts the session token in the URL fragment
 * (never sent to any server); this page stores it, wipes it from the address bar and moves on.
 */
@Component({
  selector: 'app-oauth-callback',
  imports: [RouterLink],
  template: `
  <div class="flex min-h-full items-center justify-center px-6 py-16">
    <div class="anim-rise w-full max-w-sm text-center" role="status">
      @if (error()) {
        <h1 class="text-2xl font-medium">Couldn't sign you in</h1>
        <p class="note mt-2">{{ error() }}</p>
        <a routerLink="/login" class="btn btn-primary mt-6">Back to sign in</a>
      } @else {
        <div class="skeleton mx-auto h-12 w-12 rounded-full"></div>
        <h1 class="mt-5 text-xl font-medium">Signing you in…</h1>
      }
    </div>
  </div>`,
})
export class OAuthCallbackPage implements OnInit {
  private auth = inject(AuthService);
  private router = inject(Router);
  readonly error = signal('');

  async ngOnInit() {
    const params = new URLSearchParams(window.location.hash.slice(1));
    history.replaceState(null, '', window.location.pathname);  // don't leave the token in history
    const token = params.get('token');
    if (!token) { this.error.set('The sign-in link was incomplete. Please try again.'); return; }
    try {
      await this.auth.useToken(token);
      if (!this.auth.user()) throw new Error('no session');
      await this.router.navigateByUrl(safeNext(params.get('next')) ?? '/dashboard', { replaceUrl: true });
    } catch (e) {
      this.error.set(e instanceof Error && e.message === 'no session' ? 'That sign-in has expired. Please try again.' : errorMessage(e));
    }
  }
}
