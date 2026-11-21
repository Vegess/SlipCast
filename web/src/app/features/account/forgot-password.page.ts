import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

/** No email service is set up yet, so this explains the ways back in instead of sending a reset link. */
@Component({
  selector: 'app-forgot-password',
  imports: [RouterLink],
  template: `
  <div class="flex min-h-full items-center justify-center px-6 py-16">
    <div class="anim-rise w-full max-w-md">
      <a routerLink="/" class="font-display text-xl font-bold hover:text-accent">SlipCast</a>
      <h1 class="mt-8 text-2xl font-medium">Forgot your password?</h1>
      <p class="note mt-2">SlipCast can't email reset links yet. Here are the ways back in:</p>
      <ol class="mt-6 space-y-4 text-sm">
        <li class="card p-4"><b class="font-medium">Signed up with Google or GitHub?</b>
          <span class="block text-muted">Use the same button on the sign-in page. Those accounts don't need a password.</span></li>
        <li class="card p-4"><b class="font-medium">Same email at Google or GitHub?</b>
          <span class="block text-muted">If your Google or GitHub account uses this email address and it's verified there, "Continue with…" signs you into your existing account. Then set a new password under Settings → Account.</span></li>
        <li class="card p-4"><b class="font-medium">In a team workspace?</b>
          <span class="block text-muted">Ask your workspace admin. They can send you a fresh invite link.</span></li>
      </ol>
      <a routerLink="/login" class="btn btn-primary mt-8">Back to sign in</a>
    </div>
  </div>`,
})
export class ForgotPasswordPage {}
