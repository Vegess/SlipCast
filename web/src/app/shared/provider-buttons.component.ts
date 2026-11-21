import { Component, OnInit, inject, input, signal } from '@angular/core';
import { AuthService, Provider } from '../core/auth.service';

/** "Continue with Google / GitHub". Shows only the providers the server has set up. */
@Component({
  selector: 'app-provider-buttons',
  template: `
    @if (shown().length) {
      <div class="grid gap-2.5">
        @for (p of shown(); track p.id) {
          <a [href]="auth.providerUrl(p.id, next())" class="btn w-full py-2.5">
            <span class="flex h-5 w-5 items-center justify-center rounded-full bg-fg text-[11px] font-bold text-canvas" aria-hidden="true">{{ p.mark }}</span>
            Continue with {{ p.label }}
          </a>
        }
      </div>
      <div class="my-5 flex items-center gap-3 text-xs text-muted" aria-hidden="true">
        <span class="h-px flex-1 bg-line"></span>{{ divider() }}<span class="h-px flex-1 bg-line"></span>
      </div>
    }`,
})
export class ProviderButtons implements OnInit {
  readonly auth = inject(AuthService);
  /** Where to land after signing in (a same-site path). */
  readonly next = input<string | null>(null);
  readonly divider = input('or use your email');
  readonly shown = signal<{ id: Provider; label: string; mark: string }[]>([]);

  async ngOnInit() {
    const on = await this.auth.providers();
    const all: { id: Provider; label: string; mark: string }[] = [
      { id: 'google', label: 'Google', mark: 'G' },
      { id: 'github', label: 'GitHub', mark: 'GH' },
    ];
    this.shown.set(all.filter((p) => on[p.id]));
  }
}

/** Plain-language reasons for the error codes the API's sign-in callback sends back. */
export const SIGN_IN_ERRORS: Record<string, string> = {
  cancelled: 'Sign-in was cancelled. You can try again or use your email.',
  expired: 'That sign-in took too long or was opened in a different browser. Please try again.',
  no_email: "Your account there didn't share an email address. Add one, or sign in with your email and password.",
  unverified_email: "That email address isn't verified with the provider, so it can't be used to sign in. Verify it there, or sign in with your password.",
  exchange_failed: "Couldn't finish signing in with that provider. Please try again.",
  provider_unreachable: "Couldn't reach the sign-in provider. Please try again in a moment.",
};
