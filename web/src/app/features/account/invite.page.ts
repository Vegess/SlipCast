import { Component, OnInit, inject, input, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { Api, errorMessage } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { Workspace } from '../../core/models';
import { ProviderButtons } from '../../shared/provider-buttons.component';

interface Preview { workspace_name: string; role: string; invited_by: string; valid: boolean; reason: string; }

export const ROLE_INFO: Record<'admin' | 'member' | 'viewer', { label: string; note: string }> = {
  admin: { label: 'Admin', note: 'Can change everything, including the team and who has access.' },
  member: { label: 'Member', note: 'Can add and edit projects, tickets and imports.' },
  viewer: { label: 'Viewer', note: 'Can see every project and forecast, but not change anything.' },
};

export function roleLabel(role: string): string {
  return ROLE_INFO[role as keyof typeof ROLE_INFO]?.label ?? role;
}
export function roleNote(role: string): string {
  return ROLE_INFO[role as keyof typeof ROLE_INFO]?.note ?? '';
}

/** Where an invite link lands: says what it's for, then signs in (if needed) and joins. */
@Component({
  selector: 'app-invite',
  imports: [RouterLink, ProviderButtons],
  template: `
  <div class="flex min-h-full items-center justify-center px-6 py-16">
    <div class="anim-rise w-full max-w-md">
      @if (preview(); as p) {
        <p class="pill bg-violet/15 text-violet-strong">Workspace invite</p>
        <h1 class="mt-4 text-3xl font-bold leading-tight">Join {{ p.workspace_name }}</h1>
        <p class="note mt-2">{{ p.invited_by }} invited you as <b class="text-fg">{{ roleLabel(p.role) }}</b>.
          {{ roleNote(p.role) }}</p>

        @if (!p.valid) {
          <p class="mt-6 rounded-lg border border-bad/40 bg-bad/10 px-4 py-3 text-sm text-bad">{{ p.reason }}</p>
          <a routerLink="/" class="btn mt-6">Go to SlipCast</a>
        } @else if (auth.user()) {
          <p class="note mt-6">You're signed in as {{ auth.user()!.email }}.</p>
          <button class="btn btn-primary mt-3 w-full py-2.5" (click)="accept()" [disabled]="busy()">
            {{ busy() ? 'Joining…' : 'Join ' + p.workspace_name }}</button>
          <p class="mt-3 text-center text-xs text-muted">Not you? <button class="text-info hover:underline" (click)="auth.logout()">Sign out</button></p>
        } @else {
          <div class="mt-8"><app-provider-buttons [next]="here()" divider="or" /></div>
          <div class="grid gap-2.5 sm:grid-cols-2">
            <a routerLink="/login" [queryParams]="{ next: here() }" class="btn py-2.5">Sign in</a>
            <a routerLink="/signup" [queryParams]="{ next: here() }" class="btn btn-primary py-2.5">Create an account</a>
          </div>
          <p class="mt-3 text-xs text-muted">You'll come back here to join after signing in.</p>
        }
        @if (error()) { <p class="mt-4 text-sm text-bad" role="alert">{{ error() }}</p> }
      } @else if (error()) {
        <h1 class="text-2xl font-medium">This invite doesn't work</h1>
        <p class="note mt-2">{{ error() }}</p>
        <a routerLink="/" class="btn mt-6">Go to SlipCast</a>
      } @else {
        <div class="space-y-3" role="status" aria-label="Loading invite">
          <div class="skeleton h-6 w-32"></div><div class="skeleton h-10 w-3/4"></div><div class="skeleton h-4 w-full"></div>
        </div>
      }
    </div>
  </div>`,
})
export class InvitePage implements OnInit {
  readonly auth = inject(AuthService);
  private api = inject(Api);
  private router = inject(Router);
  readonly token = input.required<string>();
  readonly preview = signal<Preview | null>(null);
  readonly busy = signal(false);
  readonly error = signal('');
  readonly roleLabel = roleLabel;
  readonly roleNote = roleNote;

  here() { return `/invite/${this.token()}`; }

  async ngOnInit() {
    await this.auth.ensureLoaded();
    try { this.preview.set(await this.api.get<Preview>(`/invites/${this.token()}`)); }
    catch (e) { this.error.set(errorMessage(e)); }
  }

  async accept() {
    this.busy.set(true); this.error.set('');
    try {
      const ws = await this.api.post<Workspace>(`/invites/${this.token()}/accept`);
      await this.auth.refresh();
      this.auth.selectWorkspace(ws.id);
      await this.router.navigateByUrl('/projects');
    } catch (e) { this.error.set(errorMessage(e)); }
    finally { this.busy.set(false); }
  }
}
