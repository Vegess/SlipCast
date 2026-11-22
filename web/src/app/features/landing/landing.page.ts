import { Component, OnDestroy, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CountUpDirective, RevealDirective, prefersReducedMotion } from '../../shared/motion';
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
  host: { '(document:keydown)': 'skipIntro()' },
  template: `
  @if (intro() !== 'off') {
    <div class="intro" [class.intro-out]="intro() === 'leaving'" (click)="skipIntro()" aria-hidden="true">
      <div class="intro-glow"></div>
      <p class="intro-logo">SlipCast</p>
      <p class="intro-tag">Every promise your business makes, forecast and scored.</p>
      <p class="intro-line">A feature ships Friday. An order arrives Tuesday. A technician comes Thursday at 2 pm.</p>
      <svg class="intro-track" viewBox="0 0 240 16" aria-hidden="true">
        <line x1="8" y1="8" x2="232" y2="8" class="intro-rail"/>
        <line x1="8" y1="8" x2="232" y2="8" class="intro-run"/>
        <circle cx="8" cy="8" r="5" class="intro-dot" style="animation-delay: .2s"/>
        <circle cx="120" cy="8" r="5" class="intro-dot" style="animation-delay: .6s"/>
        <circle cx="232" cy="8" r="5" class="intro-dot intro-dot-end" style="animation-delay: 1s"/>
      </svg>
      <button type="button" class="intro-skip" (click)="skipIntro(); $event.stopPropagation()" tabindex="-1">Skip</button>
    </div>
  }
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

    <section class="mx-auto max-w-6xl px-4 pb-14 sm:px-8">
      <div appReveal class="endcard relative overflow-hidden rounded-3xl border border-line px-6 py-14 text-center sm:px-12">
        <div class="anim-drift absolute -inset-10 -z-10 bg-[radial-gradient(circle_at_30%_20%,rgb(var(--c-accent)/0.22),transparent_55%),radial-gradient(circle_at_80%_80%,rgb(var(--c-violet)/0.2),transparent_50%)]" aria-hidden="true"></div>
        <p class="font-display text-5xl font-extrabold tracking-tight sm:text-6xl">SlipCast</p>
        <p class="mt-3 font-display text-xl text-accent sm:text-2xl">Every promise, forecast and scored.</p>
        <p class="mx-auto mt-4 max-w-xl text-muted">See your next slip before it happens. Every model is tested on work it never saw and compared with a simple baseline.</p>
        <div class="mt-7 flex flex-wrap justify-center gap-3">
          <a routerLink="/login" [queryParams]="{ demo: 1 }" class="btn btn-primary px-5 py-2.5 text-base">Try the demo</a>
          <a routerLink="/about" class="btn px-5 py-2.5 text-base">How it works</a>
        </div>
        <div class="mt-8 flex flex-col items-center gap-1.5 text-base leading-relaxed">
          <a routerLink="/" class="hover:text-accent">slip-cast.vercel.app</a>
          <a href="https://github.com/Vegess/SlipCast" target="_blank" rel="noopener" class="inline-flex items-center gap-2 hover:text-accent">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 .5a11.5 11.5 0 0 0-3.64 22.41c.58.1.79-.25.79-.56v-2c-3.2.7-3.88-1.37-3.88-1.37-.53-1.33-1.28-1.69-1.28-1.69-1.05-.71.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.7 1.26 3.36.96.1-.75.4-1.26.73-1.55-2.55-.29-5.24-1.28-5.24-5.68 0-1.26.45-2.28 1.19-3.09-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.17 1.18a11 11 0 0 1 5.77 0c2.2-1.49 3.17-1.18 3.17-1.18.63 1.59.23 2.76.11 3.05.74.81 1.19 1.83 1.19 3.09 0 4.41-2.69 5.38-5.25 5.67.41.36.78 1.06.78 2.14v3.17c0 .31.21.67.8.56A11.5 11.5 0 0 0 12 .5Z"/></svg>
            github.com/Vegess/SlipCast</a>
        </div>
        <p class="mt-5 text-sm text-muted">Angular · FastAPI · PostgreSQL · scikit-learn · Groq</p>
      </div>
      <p class="mt-8 text-center text-xs text-muted">SlipCast · open source ·
        <a routerLink="/privacy" class="hover:text-fg hover:underline">Privacy</a> ·
        <a routerLink="/terms" class="hover:text-fg hover:underline">Terms</a></p>
    </section>
  </div>`,
  styles: [`
    .intro { position: fixed; inset: 0; z-index: 60; display: flex; flex-direction: column; align-items: center; justify-content: center;
      gap: 14px; padding: 24px; text-align: center; cursor: pointer; color: #E7FBF8;
      background: radial-gradient(circle at 30% 20%, #123a36, #090D12 60%); animation: intro-in .45s ease-out both; }
    .intro-out { animation: intro-out .6s ease-in forwards; }
    .intro-glow { position: absolute; width: 520px; height: 520px; border-radius: 50%; filter: blur(80px); opacity: .35;
      background: radial-gradient(circle, #2EE6C5, transparent 60%); animation: intro-breathe 2.4s ease-in-out infinite; pointer-events: none; }
    .intro-logo { position: relative; font: 800 clamp(48px, 9vw, 84px)/1 "Bricolage Grotesque", "Instrument Sans", system-ui, sans-serif;
      letter-spacing: -1px; animation: intro-rise .7s cubic-bezier(.2,.8,.2,1) .1s both; }
    .intro-tag { position: relative; font: 500 clamp(18px, 3vw, 30px)/1.3 "Bricolage Grotesque", "Instrument Sans", system-ui, sans-serif;
      color: #2EE6C5; animation: intro-rise .7s cubic-bezier(.2,.8,.2,1) .35s both; }
    .intro-line { position: relative; max-width: 760px; font: 400 clamp(14px, 1.8vw, 19px)/1.5 "Instrument Sans", system-ui, sans-serif;
      color: #94A9B6; animation: intro-rise .7s cubic-bezier(.2,.8,.2,1) .6s both; }
    .intro-track { position: relative; width: 240px; margin-top: 10px; overflow: visible; }
    .intro-rail { stroke: #223142; stroke-width: 2; }
    .intro-run { stroke: #2EE6C5; stroke-width: 2; stroke-dasharray: 224; stroke-dashoffset: 224; animation: intro-draw 1.1s ease-out .2s forwards; }
    .intro-dot { fill: #090D12; stroke: #2EE6C5; stroke-width: 2; transform-box: fill-box; transform-origin: center; animation: intro-pop .4s cubic-bezier(.3,1.6,.5,1) both; }
    .intro-dot-end { stroke: #B78CFF; }
    .intro-skip { position: absolute; right: 24px; bottom: 20px; padding: 6px 12px; border-radius: 8px; font-size: 13px; color: #94A9B6;
      background: rgba(255,255,255,.04); border: 1px solid #223142; }
    .intro-skip:hover { color: #E7FBF8; }
    @keyframes intro-in { from { opacity: 0; } }
    @keyframes intro-out { to { opacity: 0; transform: scale(1.03); visibility: hidden; } }
    @keyframes intro-rise { from { opacity: 0; transform: translateY(16px); } }
    @keyframes intro-breathe { 50% { transform: scale(1.12); opacity: .5; } }
    @keyframes intro-draw { to { stroke-dashoffset: 0; } }
    @keyframes intro-pop { from { transform: scale(0); } }
    .endcard { background: rgb(var(--c-panel) / 0.6); }
  `],
})
export class LandingPage implements OnInit, OnDestroy {
  /** The title screen from the demo video: once per visit, skippable, never for reduced motion. */
  readonly intro = signal<'on' | 'leaving' | 'off'>('off');
  private timers: ReturnType<typeof setTimeout>[] = [];

  ngOnInit() {
    let seen = false;
    try { seen = sessionStorage.getItem('slipcast_intro') === '1'; sessionStorage.setItem('slipcast_intro', '1'); } catch { seen = true; }
    if (seen || prefersReducedMotion()) return;
    this.intro.set('on');
    this.timers.push(setTimeout(() => this.skipIntro(), 2600));
  }

  skipIntro() {
    if (this.intro() !== 'on') return;
    this.intro.set('leaving');
    this.timers.push(setTimeout(() => this.intro.set('off'), 600));
  }

  ngOnDestroy() { this.timers.forEach(clearTimeout); }
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
