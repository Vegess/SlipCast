import { Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';

const ISSUES = 'https://github.com/Vegess/SlipCast/issues';

/** Plain-language Privacy policy and Terms of use. `doc` comes from the route data. */
@Component({
  selector: 'app-legal',
  imports: [RouterLink],
  template: `
  <article class="mx-auto max-w-3xl px-4 py-10 sm:px-8">
    <p class="pill bg-raised text-muted">Last updated 21 November 2026</p>
    @if (doc() === 'privacy') {
      <h1 class="anim-rise mt-4 text-4xl font-bold">Privacy policy</h1>
      <p class="anim-rise note mt-3 text-base" style="--i: 1">SlipCast is a delivery-forecasting tool built and run by one developer as an open-source project.
        This page says what it stores, why, and who else handles it. The short version: it keeps only what it needs to work,
        it never sells or shares your data for advertising, and it has no ads or tracking.</p>

      @for (s of privacy; track s.h; let i = $index) {
        <section class="anim-rise mt-8" [style.--i]="i + 2">
          <h2 class="text-xl font-semibold">{{ s.h }}</h2>
          <ul class="mt-3 space-y-2 text-sm leading-relaxed text-fg/90">
            @for (p of s.p; track p) { <li class="flex gap-2.5"><span class="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-info" aria-hidden="true"></span><span>{{ p }}</span></li> }
          </ul>
        </section>
      }
    } @else {
      <h1 class="anim-rise mt-4 text-4xl font-bold">Terms of use</h1>
      <p class="anim-rise note mt-3 text-base" style="--i: 1">By using SlipCast you agree to these terms. They are short on purpose.</p>
      @for (s of terms; track s.h; let i = $index) {
        <section class="anim-rise mt-8" [style.--i]="i + 2">
          <h2 class="text-xl font-semibold">{{ s.h }}</h2>
          <ul class="mt-3 space-y-2 text-sm leading-relaxed text-fg/90">
            @for (p of s.p; track p) { <li class="flex gap-2.5"><span class="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" aria-hidden="true"></span><span>{{ p }}</span></li> }
          </ul>
        </section>
      }
    }
    <p class="mt-10 text-sm text-muted">Questions or requests, including deleting your account:
      <a [href]="issues" target="_blank" rel="noopener" class="text-info hover:underline">open an issue on GitHub</a>.
      See also the <a [routerLink]="doc() === 'privacy' ? '/terms' : '/privacy'" class="text-info hover:underline">{{ doc() === 'privacy' ? 'Terms of use' : 'Privacy policy' }}</a>.</p>
  </article>`,
})
export class LegalPage {
  readonly doc = input<'privacy' | 'terms'>('privacy');
  readonly issues = ISSUES;

  readonly privacy = [
    { h: 'What SlipCast stores', p: [
      'Your account: name, email address and, if you set one, a password (stored only as a bcrypt hash).',
      'If you sign in with Google or GitHub: your name, your verified email address and the account id they give SlipCast. SlipCast never sees your Google or GitHub password and does not keep their access tokens.',
      'Your work: the projects, tickets, orders or jobs you create, import or send through the API, their history, and the forecasts and alerts SlipCast makes about them.',
      'Team details: which workspaces you belong to and your role there, plus invite links (only a scrambled hash of each link is kept).',
    ] },
    { h: 'Why', p: [
      'Only to run the product: signing you in, showing your projects to the people in your workspace, and computing forecasts, risk scores and alerts.',
      'Nothing is used for advertising, sold, or shared with anyone outside the services listed below.',
    ] },
    { h: 'Who else handles it', p: [
      'Render runs the SlipCast API, and Neon hosts its PostgreSQL database (both in Singapore).',
      'Vercel serves the website.',
      'Google and GitHub, only if you choose to sign in with them.',
      'Groq, only if the server owner has enabled AI advice and privacy mode is off: computed findings, which can include ticket titles and theme names, are sent to generate suggestions. With privacy mode on, no ticket text is sent.',
    ] },
    { h: 'In your browser', p: [
      'Your session, chosen workspace, theme and privacy-mode setting are kept in your browser\'s local storage so you stay signed in.',
      'During Google or GitHub sign-in, one short-lived cookie (10 minutes) protects the sign-in from forgery. There are no analytics, advertising or tracking cookies.',
    ] },
    { h: 'Your choices', p: [
      'You can delete projects, tickets and API keys at any time in the app; deleting a project deletes its history, forecasts and alerts.',
      'You can leave a workspace from Settings → Team, and sign out of every device from Settings → Account.',
      'To delete your whole account, or to get a copy of your data, open an issue on GitHub and it will be handled by hand. Project data can also be exported to Excel or CSV from the Delivery tab.',
    ] },
    { h: 'Changes', p: ['If this policy changes in a way that matters, the date at the top changes and the change is noted in the project\'s changelog on GitHub.'] },
  ];

  readonly terms = [
    { h: 'What SlipCast is', p: [
      'An open-source portfolio project offered free of charge, as is, with no warranty of any kind.',
      'Forecasts, risk scores and advice are statistical estimates from your own history. They can be wrong; SlipCast shows its own track record so you can judge how far to trust it. Don\'t rely on it alone for decisions with serious consequences.',
    ] },
    { h: 'Your account and your data', p: [
      'Keep your password and API keys secret; anything done with them counts as done by you.',
      'You keep all rights to the data you put in. You give SlipCast permission to store and process it only to provide the service to you and your workspace.',
      'Workspace admins decide who can see a workspace\'s data. Invite only people you trust with it.',
    ] },
    { h: 'Fair use', p: [
      'Don\'t use SlipCast for anything unlawful, to store other people\'s personal data without the right to do so, or to attack or overload the service.',
      'The event API is limited to 600 events a minute per key. Accounts or keys that abuse the service may be suspended.',
    ] },
    { h: 'Availability', p: [
      'SlipCast runs on free hosting tiers: it may be slow to wake up, have downtime, or change or end at any time. Export anything you want to keep.',
      'To the extent the law allows, the developer is not liable for any loss arising from using SlipCast.',
    ] },
    { h: 'The code', p: ['SlipCast\'s source code is available on GitHub under the MIT License.'] },
  ];
}
