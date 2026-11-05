import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

interface Feature { imgCls?: string; kicker: string; title: string; body: string; points: string[]; img: string; alt: string; edge: string; kickerCls: string; }

const FEATURES: Feature[] = [
  {
    kicker: 'Reference-class forecasts', title: '"Tickets like this took 4–15 days. You planned 2."',
    body: 'For any ticket, SlipCast finds the most similar finished tickets by their text and shows how long they really took. It is reference-class forecasting, the antidote to the planning fallacy, applied to every ticket.',
    points: ['The 20 closest finished tickets, with the 3 nearest shown', 'Flags plans shorter than what 3 in 4 similar tickets needed', 'Says "not enough similar history" instead of guessing'],
    img: 'landing/reference.webp', imgCls: 'mx-auto max-w-[320px]', alt: 'Ticket check panel showing similar tickets took 4 to 15 days against a 2-day plan', edge: 'border-t-info', kickerCls: 'text-info',
  },
  {
    kicker: 'Write-time risk check', title: 'Catch the slip while the ticket is still being written.',
    body: 'Other tools tell you a project is late after the fact. As someone types a new ticket, SlipCast scores how ready it is, predicts the chance it misses its date, explains why, and spots duplicates. Fixing it then costs nothing.',
    points: ['0–100 readiness score with the reasons', 'Slip risk from a model trained on your own history', 'Suggests a clearer rewrite, and never blocks saving'],
    img: 'landing/check.webp', alt: 'New ticket dialog with a live check panel showing quality score, reference class and a 76% slip risk', edge: 'border-t-violet', kickerCls: 'text-violet',
  },
  {
    kicker: 'Forecast ledger', title: 'Every forecast is scored. Honesty is a feature.',
    body: 'SlipCast stores every forecast it makes and checks it automatically when the work finishes. Your team sees its real hit rate and whether "85% likely" really comes true about 85% of the time.',
    points: ['Completion dates and ticket durations, both scored', 'Calibration chart: stated odds versus what happened', 'Accuracy measured on your tickets, not promised'],
    img: 'landing/track-record.webp', alt: 'Track record section showing an 83% hit rate and a calibration chart', edge: 'border-t-accent', kickerCls: 'text-accent',
  },
];

@Component({
  selector: 'app-landing',
  imports: [RouterLink],
  template: `
  <div class="overflow-x-hidden">
    <section class="mx-auto grid max-w-6xl items-center gap-10 px-4 pb-16 pt-14 sm:px-8 lg:grid-cols-[1fr_1.1fr] lg:pt-20">
      <div>
        <p class="pill bg-accent/15 text-accent-strong">Delivery analytics for software teams</p>
        <h1 class="mt-5 text-4xl font-bold leading-[1.05] sm:text-6xl">Other tools tell you a project is late.</h1>
        <p class="mt-5 text-lg text-fg/90 sm:text-xl">
          SlipCast tells you a <span class="text-accent">ticket</span> will be late while you're still writing it,
          and proves how often it's right.
        </p>
        <p class="mt-4 max-w-lg text-muted">Import ticket history from Jira, GitHub Issues, Trello or Linear as a CSV. No plugin, and a privacy mode that never sends ticket text to an AI.</p>
        <div class="mt-8 flex flex-wrap gap-3">
          <a routerLink="/login" [queryParams]="{ demo: 1 }" class="btn btn-primary px-5 py-2.5 text-base">Try the demo</a>
          <a routerLink="/login" class="btn px-5 py-2.5 text-base">Sign in</a>
          <a routerLink="/about" class="btn btn-ghost px-4 py-2.5 text-base text-muted">How it works →</a>
        </div>
        <p class="mt-4 text-xs text-muted">The demo loads six months of tickets from a SaaS billing team. Free, no card.</p>
      </div>
      <figure class="relative">
        <div class="absolute -inset-6 -z-10 rounded-[2rem] bg-gradient-to-br from-info/25 via-violet/15 to-accent/20 blur-2xl" aria-hidden="true"></div>
        <img src="landing/delivery.webp" width="1200" height="750" class="w-full rounded-xl border border-line shadow-2xl"
             alt="SlipCast Delivery tab with cycle time, throughput and forecast numbers">
      </figure>
    </section>

    <section class="border-y border-line bg-panel/60">
      <div class="mx-auto grid max-w-6xl gap-6 px-4 py-8 text-center sm:grid-cols-3 sm:px-8">
        <div><p class="font-display text-3xl text-ok">92%</p><p class="note">ticket types predicted correctly (vs 37% baseline)</p></div>
        <div><p class="font-display text-3xl text-info">83%</p><p class="note">of real durations inside the "took X–Y days" range</p></div>
        <div><p class="font-display text-3xl text-accent">83%</p><p class="note">of forecasts within their 85% estimate, on the demo's replayed history</p></div>
      </div>
    </section>

    @for (f of features; track f.kicker; let i = $index) {
      <section class="mx-auto grid max-w-6xl items-center gap-10 px-4 py-16 sm:px-8 lg:grid-cols-2">
        <div [class.lg:order-2]="i % 2 === 1">
          <p class="text-sm font-semibold uppercase tracking-wide" [class]="f.kickerCls">{{ f.kicker }}</p>
          <h2 class="mt-3 text-3xl font-bold leading-tight">{{ f.title }}</h2>
          <p class="mt-4 text-muted">{{ f.body }}</p>
          <ul class="mt-5 space-y-2 text-sm">
            @for (p of f.points; track p) { <li class="flex gap-2.5"><span class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-current" [class]="f.kickerCls" aria-hidden="true"></span>{{ p }}</li> }
          </ul>
        </div>
        <img [src]="f.img" [alt]="f.alt" loading="lazy" class="w-full rounded-xl border border-line border-t-2 shadow-xl" [class]="f.edge + ' ' + (f.imgCls ?? '')">
      </section>
    }

    <section class="mx-auto max-w-6xl px-4 pb-20 sm:px-8">
      <div class="card card-accent flex flex-col items-start gap-5 p-8 sm:flex-row sm:items-center">
        <div class="mr-auto">
          <h2 class="text-2xl font-bold">See your next slip before it happens.</h2>
          <p class="note mt-1">Every model is tested on tickets it never saw and compared with a simple baseline. Read how each one works.</p>
        </div>
        <a routerLink="/about" class="btn">How it works</a>
        <a routerLink="/login" [queryParams]="{ demo: 1 }" class="btn btn-primary">Try the demo</a>
      </div>
      <p class="mt-8 text-center text-xs text-muted">SlipCast · open source · Angular, FastAPI, PostgreSQL, scikit-learn</p>
    </section>
  </div>`,
})
export class LandingPage {
  readonly features = FEATURES;
}
