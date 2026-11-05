import { Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { AuthService } from '../../core/auth.service';

interface Method { id: string; title: string; tag: 'Analytics' | 'Forecast' | 'Model' | 'AI'; what: string; how: string; why: string; }

const TAG_STYLE: Record<Method['tag'], string> = {
  Analytics: 'card-info',
  Forecast: 'card-accent',
  Model: 'card-violet',
  AI: 'card-violet',
};

const METHODS: Method[] = [
  {
    id: 'history', title: 'Ticket history', tag: 'Analytics',
    what: 'Everything starts from when each ticket was created, started, blocked and finished.',
    how: 'Every status change is stored as an event. CSV imports from Jira, GitHub Issues, Trello or Linear are mapped automatically, and a data-quality report shows what was kept, skipped or guessed.',
    why: 'Forecasts are only as honest as the history underneath them, so the quality of that history is always visible.',
  },
  {
    id: 'cycle', title: 'Cycle time and percentiles', tag: 'Analytics',
    what: 'How long a ticket takes from the moment someone starts it until it is done.',
    how: 'SlipCast reports the 50th, 85th and 95th percentiles instead of the average. "85% of tickets finish within 11 days" means 17 out of 20 did.',
    why: 'A few very slow tickets drag the average up, so the average is a promise you will miss more than half the time.',
  },
  {
    id: 'flow', title: 'Throughput and cumulative flow', tag: 'Analytics',
    what: 'How many tickets the team finishes each week, and how many sit in each status day by day.',
    how: 'Throughput counts finished tickets per week. The cumulative flow chart rebuilds every ticket\'s status at the end of each day from its history.',
    why: 'A steady weekly pace makes forecasting possible; a widening in-progress band shows work piling up.',
  },
  {
    id: 'montecarlo', title: 'Monte Carlo forecast', tag: 'Forecast',
    what: 'A date for when all the open tickets will be done, with the odds attached.',
    how: 'SlipCast replays the future 10,000 times. In each run it picks random weeks from your last 12 weeks of throughput until the remaining tickets are done. The spread of finish dates gives the 50%, 85% and 95% dates.',
    why: 'It uses your real pace and its real ups and downs, instead of estimates or story points.',
  },
  {
    id: 'reference', title: 'Reference-class forecast for each ticket', tag: 'Forecast',
    what: '"Tickets like this took 4–15 days (n=20). You planned 2."',
    how: 'SlipCast compares the words in a ticket with every finished ticket (TF-IDF, a standard way to weigh distinctive words) and takes the 20 most similar. Their real durations form the range. If fewer than 8 are similar enough, it says so instead of guessing.',
    why: 'People plan from the best case. Looking at what happened to similar work, an idea from Kahneman and Flyvbjerg, corrects that before work starts.',
  },
  {
    id: 'quality', title: 'Write-time ticket check', tag: 'Model',
    what: 'While you type a new ticket, a panel scores it and warns about risk before anyone starts.',
    how: 'A 0–100 readiness score loses points for a short or vague title, a missing description, no acceptance criteria or reproduction steps, no owner or no due date. The same panel shows the reference-class range, the chance of slipping and likely duplicates.',
    why: 'Most tools spot problems after a ticket is already late. Fixing a vague ticket or an unrealistic date costs almost nothing at the moment it is written.',
  },
  {
    id: 'risk', title: 'Slip-risk model', tag: 'Model',
    what: 'The chance an open ticket will finish after its due date, with the main reasons.',
    how: 'A logistic regression learns from your finished tickets, using only facts known when a ticket is created: how long it was planned for, how many open tickets its owner already had, the ticket text and quality, priority and type. The reasons shown are the factors pushing that ticket\'s risk up the most.',
    why: 'A simple, transparent model can be checked and explained, so "76% because the plan is 2 days and Arun already has 16 open tickets" is literally how the number was produced.',
  },
  {
    id: 'text', title: 'Types, themes and duplicates', tag: 'Model',
    what: 'Ticket types for unlabelled tickets, themes found in the text, and tickets that look like repeats.',
    how: 'A text classifier learns types from labelled tickets. Clustering groups tickets that use similar words into themes, named by their strongest words. Pairs of tickets whose text is at least 72% similar are flagged as possible duplicates.',
    why: 'Delivery problems often live in the words: one area of the product may slip far more than others, and nobody tagged it.',
  },
  {
    id: 'ledger', title: 'Forecast ledger', tag: 'Forecast',
    what: 'A record of every forecast SlipCast has made for your team, and whether it came true.',
    how: 'Each forecast is stored when it is made. When the work finishes, SlipCast scores it automatically and shows the hit rate and a calibration chart: when it said 85%, did it come true about 85% of the time?',
    why: 'You shouldn\'t have to trust a forecasting tool on faith. The ledger shows how accurate it has been on your own tickets.',
  },
  {
    id: 'evaluation', title: 'How the models are tested', tag: 'Model',
    what: 'Every model is scored on tickets it never saw, against a simple baseline.',
    how: 'Models train on older tickets and are tested on newer ones, the way they are used in real life. Each result is shown next to a trivial alternative, such as always guessing the most common type.',
    why: 'Testing on the future, not a random sample, keeps the numbers honest. A metric without a baseline means nothing.',
  },
  {
    id: 'advice', title: 'AI advice, kept on a short leash', tag: 'AI',
    what: 'Three to five concrete actions for the week, and a weekly status report.',
    how: 'An LLM receives numbered findings that the models computed, never your raw data, and must cite the findings each suggestion is based on. A checker rejects any suggestion that cites nothing or uses a number that isn\'t in the findings. Without an AI key, or if the AI\'s answer fails the check, built-in rules write the advice.',
    why: 'The models measure; the AI only writes. That keeps advice grounded in facts you can see.',
  },
  {
    id: 'privacy', title: 'Privacy mode', tag: 'AI',
    what: 'A switch that keeps ticket text away from the AI.',
    how: 'With privacy mode on, findings sent to the AI contain no ticket titles or theme names, and ticket rewrites use a template instead of the AI.',
    why: 'Ticket text can contain customer names or confidential plans. You decide what leaves the server.',
  },
];

@Component({
  selector: 'app-about',
  imports: [RouterLink],
  template: `
  <div class="mx-auto max-w-4xl px-4 py-10 sm:px-8">
    <p class="text-sm font-medium text-accent">How SlipCast works</p>
    <h1 class="mt-2 text-4xl font-bold leading-tight">Measured by models. Explained in plain language.</h1>
    <p class="mt-4 max-w-2xl text-muted">
      SlipCast answers two questions: when will this really be done, and which tickets are going to slip, and why?
      Here is every method it uses, what it tells you, and why it is built that way.
    </p>
    <nav aria-label="Methods" class="mt-8 flex flex-wrap gap-2">
      @for (m of methods; track m.id) { <a [href]="'#' + m.id" (click)="jump($event, m.id)" class="pill bg-raised text-muted hover:text-fg">{{ m.title }}</a> }
    </nav>

    <div class="mt-10 grid gap-5">
      @for (m of methods; track m.id; let i = $index) {
        <section [id]="m.id" class="card scroll-mt-6" [class]="tagStyle[m.tag]">
          <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span class="font-display text-sm text-muted">{{ (i + 1).toString().padStart(2, '0') }}</span>
            <h2 class="text-xl font-medium">{{ m.title }}</h2>
            <span class="pill bg-raised text-muted">{{ m.tag }}</span>
          </div>
          <dl class="mt-4 grid gap-3 text-sm sm:grid-cols-[110px_1fr]">
            <dt class="font-medium text-muted">What it tells you</dt><dd>{{ m.what }}</dd>
            <dt class="font-medium text-muted">How it works</dt><dd class="text-fg/90">{{ m.how }}</dd>
            <dt class="font-medium text-muted">Why this way</dt><dd class="text-fg/90">{{ m.why }}</dd>
          </dl>
        </section>
      }
    </div>

    <section class="card card-accent mt-10 flex flex-wrap items-center gap-4">
      <div class="mr-auto">
        <h2 class="section-title">See it on real-looking data</h2>
        <p class="note">The demo loads six months of tickets from a SaaS billing team, so every method above has something to show.</p>
      </div>
      @if (auth.user()) { <a routerLink="/dashboard" class="btn btn-primary">Go to your dashboard</a> }
      @else { <a routerLink="/login" [queryParams]="{ demo: 1 }" class="btn btn-primary">Try the demo</a> }
    </section>
  </div>`,
})
export class AboutPage {
  readonly auth = inject(AuthService);
  readonly methods = METHODS;
  readonly tagStyle = TAG_STYLE;

  /** In-page links: scroll inside the layout's scroll container without changing the route. */
  jump(ev: Event, id: string) {
    ev.preventDefault();
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}
