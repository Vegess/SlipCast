import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CountUpDirective, RevealDirective } from '../../shared/motion';
import { StoryDiagram } from '../../shared/story-diagram.component';

interface Feature { imgCls?: string; kicker: string; title: string; body: string; points: string[]; img: string; alt: string; edge: string; kickerCls: string; }

const FEATURES: Feature[] = [
  {
    kicker: 'Reference-class forecasts', title: '"Tickets like this took 4–15 days. You planned 2."',
    body: 'For every promise, SlipCast finds the most similar finished ones and shows how long they really took. It is reference-class forecasting, the antidote to the planning fallacy: similar tickets by their text, orders on the same route and carrier, jobs of the same service by the same technician.',
    points: ['"Orders like this on this route took 3–6 days"', '"AC repair jobs by Manoj took 1.5–3 hours"', 'Says "not enough similar history" instead of guessing'],
    img: 'landing/reference.webp', imgCls: 'mx-auto max-w-[320px]', alt: 'Ticket check panel showing similar tickets took 4 to 15 days against a 2-day plan', edge: 'border-t-info', kickerCls: 'text-info',
  },
  {
    kicker: 'Write-time risk check', title: 'Catch the slip before the promise is made.',
    body: 'Other tools tell you something is late after the fact. While someone writes a ticket, promises a delivery date or books a visit, SlipCast shows how long similar ones really took and the chance this one is missed, with the reasons. Fixing it then costs nothing.',
    points: ['Tickets: a 0–100 readiness score, slip risk and a clearer rewrite', 'Orders: how many similar orders would have missed this date, and the best carrier on the route', 'Visits: real job length and how busy the technician already is that day'],
    img: 'landing/check.webp', alt: 'New ticket dialog with a live check panel showing quality score, reference class and a 76% slip risk', edge: 'border-t-violet', kickerCls: 'text-violet',
  },
  {
    kicker: 'Forecast ledger', title: 'Every forecast is scored. Honesty is a feature.',
    body: 'SlipCast stores every forecast it makes and checks it automatically when the work finishes. You see its real hit rate per module, and whether "85% likely" really comes true about 85% of the time.',
    points: ['Completion dates and durations, both scored', 'Calibration chart: stated odds versus what happened', 'Accuracy measured on your own work, not promised'],
    img: 'landing/track-record.webp', alt: 'Track record section showing an 83% hit rate and a calibration chart', edge: 'border-t-accent', kickerCls: 'text-accent',
  },
];

@Component({
  selector: 'app-landing',
  imports: [RouterLink, RevealDirective, CountUpDirective, StoryDiagram],
  template: `
  <div class="overflow-x-hidden">
    <section class="mx-auto grid max-w-6xl items-center gap-10 px-4 pb-16 pt-14 sm:px-8 lg:grid-cols-[1fr_1.1fr] lg:pt-20">
      <div>
        <p class="anim-rise pill gap-2 bg-accent/15 text-accent-strong">
          <span class="relative flex h-2 w-2" aria-hidden="true"><span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-60"></span><span class="relative inline-flex h-2 w-2 rounded-full bg-accent"></span></span>
          Delivery forecasting for software, orders and service visits</p>
        <h1 class="anim-rise mt-5 text-4xl font-bold leading-[1.05] sm:text-6xl" style="--i: 1">Every promise your business makes, forecast and scored.</h1>
        <p class="anim-rise mt-5 text-lg text-fg/90 sm:text-xl" style="--i: 3">
          A feature ships <span class="text-info">Friday</span>. An order arrives <span class="text-accent">Tuesday</span>.
          A technician comes <span class="text-violet">Thursday at 2 pm</span>. SlipCast tells you which of those promises
          will slip while there's still time to act, and proves how often it's right.
        </p>
        <p class="anim-rise mt-4 max-w-lg text-muted" style="--i: 4">Connect GitHub, send stage updates from your order or booking system, or import tickets as a CSV. No plugin, and a privacy mode that never sends text to an AI.</p>
        <div class="anim-rise mt-8 flex flex-wrap gap-3" style="--i: 5">
          <a routerLink="/login" [queryParams]="{ demo: 1 }" class="btn btn-primary px-5 py-2.5 text-base">Try the demo</a>
          <a routerLink="/login" class="btn px-5 py-2.5 text-base">Sign in</a>
          <a routerLink="/about" class="btn btn-ghost px-4 py-2.5 text-base text-muted">How it works →</a>
        </div>
        <p class="anim-fade mt-4 text-xs text-muted" style="--i: 8">The demo opens a software team; add demo orders and service visits from New project. Free, no card.</p>
      </div>
      <figure class="anim-pop relative" style="animation-delay: 0.25s; animation-duration: 0.8s">
        <div class="anim-drift absolute -inset-6 -z-10 rounded-[2rem] bg-gradient-to-br from-info/25 via-violet/15 to-accent/20 blur-2xl" aria-hidden="true"></div>
        <img src="landing/control-room.webp" width="1200" height="750" class="anim-float w-full rounded-xl border border-line shadow-2xl"
             alt="SlipCast Control Room: promises due this week across software, orders and service visits, riskiest first">
      </figure>
    </section>

    <section class="border-y border-line bg-panel/60">
      <div class="mx-auto grid max-w-6xl gap-6 px-4 py-8 text-center sm:grid-cols-3 sm:px-8">
        <div appReveal="0"><p class="font-display text-3xl text-info tabular-nums" [appCountUp]="85" suffix="%">85%</p><p class="note"><b class="text-fg">Build:</b> late tickets ranked above on-time ones (vs 79% for a simple rule)</p></div>
        <div appReveal="1"><p class="font-display text-3xl text-accent tabular-nums" [appCountUp]="87" suffix="%">87%</p><p class="note"><b class="text-fg">Ship:</b> late orders ranked above on-time ones (vs 85% for the carrier's record alone)</p></div>
        <div appReveal="2"><p class="font-display text-3xl text-violet tabular-nums" [appCountUp]="76" suffix="%">76%</p><p class="note"><b class="text-fg">Serve:</b> missed visits ranked above on-time ones (vs 62% for the technician's record alone)</p></div>
      </div>
      <p class="mx-auto max-w-6xl px-4 pb-6 text-center text-xs text-muted sm:px-8">Measured on the demo data, each model tested only on newer work it never saw. The baseline is always shown.</p>
    </section>

    <section class="mx-auto max-w-6xl px-4 pt-16 sm:px-8">
      <div appReveal class="max-w-2xl">
        <p class="text-sm font-semibold uppercase tracking-wide text-accent">One engine, three modules</p>
        <h2 class="mt-3 text-3xl font-bold leading-tight">Every kind of promise, the same honest forecasting.</h2>
        <p class="mt-3 text-muted">Each promise has stages, a promised date and a real finish. Pick a module per project; the Control Room shows them all together.</p>
      </div>
      <div class="mt-8 grid gap-4 md:grid-cols-3">
        @for (m of modules; track m.name; let i = $index) {
          <div [appReveal]="i" class="card lift border-t-2 p-5" [class]="m.edge">
            <p class="font-display text-xl font-semibold" [class]="m.cls">{{ m.name }}</p>
            <p class="mt-1 text-sm text-muted">{{ m.what }}</p>
            <p class="mt-4 text-sm">"{{ m.quote }}"</p>
            <p class="mt-3 text-xs text-muted">{{ m.extra }}</p>
          </div>
        }
      </div>
    </section>

    <section class="mx-auto max-w-6xl px-4 pt-16 sm:px-8">
      <div appReveal class="max-w-2xl">
        <p class="text-sm font-semibold uppercase tracking-wide text-info">How it reads a ticket</p>
        <h2 class="mt-3 text-3xl font-bold leading-tight">From a sentence you type to a forecast that keeps score.</h2>
        <p class="mt-3 text-muted">Four steps, a few hundred milliseconds, and no story points.</p>
      </div>
      <div class="mt-8"><app-story-diagram /></div>
    </section>

    @for (f of features; track f.kicker; let i = $index) {
      <section class="mx-auto grid max-w-6xl items-center gap-10 px-4 py-16 sm:px-8 lg:grid-cols-2">
        <div appReveal [class.lg:order-2]="i % 2 === 1">
          <p class="text-sm font-semibold uppercase tracking-wide" [class]="f.kickerCls">{{ f.kicker }}</p>
          <h2 class="mt-3 text-3xl font-bold leading-tight">{{ f.title }}</h2>
          <p class="mt-4 text-muted">{{ f.body }}</p>
          <ul class="mt-5 space-y-2 text-sm">
            @for (p of f.points; track p) { <li class="flex gap-2.5"><span class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-current" [class]="f.kickerCls" aria-hidden="true"></span>{{ p }}</li> }
          </ul>
        </div>
        <div appReveal="1"><img [src]="f.img" [alt]="f.alt" loading="lazy" class="lift w-full rounded-xl border border-line border-t-2 shadow-xl" [class]="f.edge + ' ' + (f.imgCls ?? '')"></div>
      </section>
    }

    <section class="mx-auto max-w-6xl px-4 pb-20 sm:px-8">
      <div appReveal class="card card-accent flex flex-col items-start gap-5 p-8 sm:flex-row sm:items-center">
        <div class="mr-auto">
          <h2 class="text-2xl font-bold">See your next slip before it happens.</h2>
          <p class="note mt-1">Every model is tested on work it never saw and compared with a simple baseline. Read how each one works.</p>
        </div>
        <a routerLink="/about" class="btn">How it works</a>
        <a routerLink="/login" [queryParams]="{ demo: 1 }" class="btn btn-primary">Try the demo</a>
      </div>
      <p class="mt-8 text-center text-xs text-muted">SlipCast · open source · Angular, FastAPI, PostgreSQL, scikit-learn ·
        <a routerLink="/privacy" class="hover:text-fg hover:underline">Privacy</a> ·
        <a routerLink="/terms" class="hover:text-fg hover:underline">Terms</a></p>
    </section>
  </div>`,
})
export class LandingPage {
  readonly features = FEATURES;
  readonly modules = [
    { name: 'Build', cls: 'text-info', edge: 'border-t-info', what: 'Software tickets, pull requests and releases.',
      quote: 'Tickets like this took 4–15 days. You planned 2.', extra: 'Monte Carlo forecasts, review wait, the four DORA metrics, GitHub webhook.' },
    { name: 'Ship', cls: 'text-accent', edge: 'border-t-accent', what: 'Customer orders, from ordered to delivered.',
      quote: 'Orders like this to Guwahati took 5–11 days. You promised 2.', extra: 'On-time rate by carrier and route, where orders wait, late-delivery risk.' },
    { name: 'Serve', cls: 'text-violet', edge: 'border-t-violet', what: 'Service visits, from booked to done.',
      quote: 'AC repair jobs took 2–4 hours. You booked 2.', extra: 'Missed-visit risk, real job length vs booked, technician load.' },
  ];
}
