import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Api, errorMessage } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { ThemeService } from '../../core/theme.service';
import { WorkspaceStore } from '../../core/workspace.store';

interface AiStatus { provider: 'groq' | 'rules'; configured: boolean; model: string | null; limits: { per_minute: number; per_day: number }; }

@Component({
  selector: 'app-settings',
  imports: [FormsModule],
  template: `
  <div class="mx-auto max-w-3xl px-4 py-8 sm:px-8">
    <h1 class="text-3xl font-bold">Settings</h1>
    <p class="note mt-1">Your profile and how SlipCast behaves in this browser.</p>

    <section class="card card-info mt-8">
      <h2 class="section-title">Profile</h2>
      <form class="mt-4 grid gap-4 sm:grid-cols-[1fr_auto] sm:items-end" (ngSubmit)="saveName()">
        <label class="label">Name <input class="input" name="name" [(ngModel)]="name" maxlength="80" required></label>
        <button class="btn btn-primary" [disabled]="saving() || !name.trim() || name.trim() === auth.user()?.name">{{ saving() ? 'Saving…' : 'Save name' }}</button>
      </form>
      <p class="note mt-3">Signed in as {{ auth.user()?.email }} · {{ auth.workspace()?.name }}</p>
      @if (saved()) { <p class="mt-2 text-sm text-ok" role="status">Name saved.</p> }
      @if (error()) { <p class="mt-2 text-sm text-bad">{{ error() }}</p> }
    </section>

    <section class="card card-violet mt-5">
      <h2 class="section-title">Privacy</h2>
      <label class="mt-4 flex cursor-pointer items-start gap-3 text-sm">
        <input type="checkbox" class="mt-1 accent-accent" [checked]="store.privacyMode()" (change)="store.setPrivacy($any($event.target).checked)">
        <span><b class="font-medium">Privacy mode</b>
          <span class="block text-muted">Ticket titles and theme names are never sent to the AI, and ticket rewrites use a built-in template instead. Saved in this browser.</span></span>
      </label>
    </section>

    <section class="card card-accent mt-5">
      <h2 class="section-title">Appearance</h2>
      <div class="mt-4 flex flex-wrap gap-3" role="radiogroup" aria-label="Theme">
        @for (t of themes; track t.id) {
          <button type="button" role="radio" [attr.aria-checked]="theme.theme() === t.id" (click)="theme.set(t.id)"
                  class="flex min-w-[180px] items-center gap-3 rounded-xl border px-4 py-3 text-left"
                  [class.border-accent]="theme.theme() === t.id" [class.border-line]="theme.theme() !== t.id">
            <span class="flex h-8 w-8 overflow-hidden rounded-lg ring-1 ring-line" aria-hidden="true">
              <span class="w-1/2" [style.background]="t.swatch[0]"></span><span class="w-1/2" [style.background]="t.swatch[1]"></span>
            </span>
            <span><span class="block text-sm font-medium">{{ t.label }}</span><span class="block text-xs text-muted">{{ t.note }}</span></span>
          </button>
        }
      </div>
    </section>

    <section class="card card-violet mt-5">
      <h2 class="section-title">AI advice</h2>
      @if (ai(); as a) {
        <p class="mt-3 flex items-center gap-2 text-sm">
          <span class="h-2.5 w-2.5 rounded-full" [class.bg-ok]="a.configured" [class.bg-muted]="!a.configured" aria-hidden="true"></span>
          @if (a.configured) { <span>Connected to Groq · <span class="text-muted">{{ a.model }}</span></span> }
          @else { <span>Rule-based advice <span class="text-muted">(no AI key configured on the server)</span></span> }
        </p>
        <p class="note mt-2">
          @if (a.configured) {
            The AI only turns computed findings into suggestions, and every suggestion is checked before you see it.
            Limits: {{ a.limits.per_minute }} requests a minute and {{ a.limits.per_day }} a day per person; past that, rule-based advice is used.
          } @else {
            Everything works without an AI key: advice, status reports and rewrites come from built-in rules and templates.
            The server owner can add a Groq key (GROQ_API_KEY) to enable AI-written suggestions.
          }
        </p>
      } @else { <p class="note mt-3">Checking…</p> }
    </section>
  </div>`,
})
export class SettingsPage implements OnInit {
  readonly auth = inject(AuthService);
  readonly store = inject(WorkspaceStore);
  readonly theme = inject(ThemeService);
  private api = inject(Api);
  readonly ai = signal<AiStatus | null>(null);
  readonly saving = signal(false);
  readonly saved = signal(false);
  readonly error = signal('');
  name = '';
  readonly themes = [
    { id: 'dusk' as const, label: 'Dusk', note: 'Soft dark (default)', swatch: ['#1F2A40', '#6EA8FE'] },
    { id: 'light' as const, label: 'Light', note: 'For bright rooms', swatch: ['#FFFFFF', '#2459D6'] },
  ];

  ngOnInit() {
    this.name = this.auth.user()?.name ?? '';
    this.api.get<AiStatus>('/auth/ai-status').then((a) => this.ai.set(a)).catch((e) => this.error.set(errorMessage(e)));
  }

  async saveName() {
    this.saving.set(true); this.saved.set(false); this.error.set('');
    try { await this.auth.updateName(this.name.trim()); this.saved.set(true); }
    catch (e) { this.error.set(errorMessage(e)); }
    finally { this.saving.set(false); }
  }
}
