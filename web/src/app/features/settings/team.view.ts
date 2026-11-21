import { Component, effect, inject, signal, untracked } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { Api, errorMessage } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { longDate } from '../../shared/format';
import { ROLE_INFO, roleLabel } from '../account/invite.page';

interface Member { user_id: string; name: string; email: string; role: string; is_you: boolean; }
interface Invite { id: string; role: string; created_at: string; expires_at: string; url: string | null; }

@Component({
  selector: 'app-team-settings',
  imports: [FormsModule],
  template: `
  <section class="card card-info anim-rise">
    <div class="flex flex-wrap items-baseline justify-between gap-2">
      <h2 class="section-title">People in {{ auth.workspace()?.name }}</h2>
      <span class="pill bg-raised text-muted">You are {{ roleLabel(auth.role()).toLowerCase() }}</span>
    </div>
    <p class="note mt-1">Admins manage the team. Members add and edit work. Viewers can see everything but change nothing.</p>
    <ul class="mt-4 divide-y divide-line/70">
      @for (m of members(); track m.user_id; let i = $index) {
        <li class="anim-rise flex flex-wrap items-center gap-3 py-3" [style.--i]="i">
          <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-raised text-sm font-semibold" aria-hidden="true">{{ m.name.charAt(0).toUpperCase() }}</span>
          <span class="min-w-0 flex-1">
            <span class="block truncate text-sm font-medium">{{ m.name }} @if (m.is_you) { <span class="text-muted">(you)</span> }</span>
            <span class="block truncate text-xs text-muted">{{ m.email }}</span>
          </span>
          @if (auth.isAdmin()) {
            <select class="input w-auto py-1.5" [ngModel]="m.role" (ngModelChange)="setRole(m, $event)" [attr.aria-label]="'Role for ' + m.name">
              @for (r of roles; track r) { <option [value]="r">{{ roleInfo[r].label }}</option> }
            </select>
            @if (!m.is_you) { <button class="btn btn-ghost px-2 text-muted" (click)="remove(m)" [attr.aria-label]="'Remove ' + m.name">Remove</button> }
          } @else {
            <span class="pill bg-raised text-muted">{{ roleLabel(m.role) }}</span>
          }
          @if (m.is_you && members().length > 1 && (m.role !== 'admin' || adminCount() > 1)) {
            <button class="btn btn-ghost px-2 text-muted" (click)="leave(m)">Leave</button>
          }
        </li>
      } @empty {
        @if (!error()) { @for (i of [0, 1]; track i) { <li class="py-3"><div class="skeleton h-9 w-full"></div></li> } }
      }
    </ul>
    @if (error()) { <p class="mt-3 text-sm text-bad" role="alert">{{ error() }}</p> }
  </section>

  @if (auth.isAdmin()) {
    <section class="card card-violet anim-rise mt-5" style="--i: 1">
      <h2 class="section-title">Invite someone</h2>
      <p class="note mt-1">Make a link and send it however you like. It works once and expires in 7 days.</p>
      <div class="mt-4 flex flex-wrap items-end gap-3">
        <label class="label">Their role
          <select class="input w-auto" [(ngModel)]="newRole" name="role">
            @for (r of roles; track r) { <option [value]="r">{{ roleInfo[r].label }}</option> }
          </select>
        </label>
        <button class="btn btn-primary" (click)="createInvite()" [disabled]="busy()">{{ busy() ? 'Making link…' : 'Make invite link' }}</button>
      </div>
      <p class="mt-2 text-xs text-muted">{{ roleInfo[newRole].note }}</p>

      @if (fresh(); as f) {
        <div class="anim-pop mt-4 rounded-lg border border-accent/50 bg-accent/10 p-3">
          <p class="text-sm font-medium">Copy this link now. For security it won't be shown again.</p>
          <div class="mt-2 flex gap-2">
            <input class="input font-mono text-xs" [value]="f.url" readonly (focus)="$any($event.target).select()" aria-label="Invite link">
            <button class="btn shrink-0" (click)="copy(f.url!)">{{ copied() ? 'Copied ✓' : 'Copy' }}</button>
          </div>
        </div>
      }

      @if (invites().length) {
        <h3 class="mt-6 text-sm font-medium">Links not used yet</h3>
        <ul class="mt-2 divide-y divide-line/70 text-sm">
          @for (inv of invites(); track inv.id) {
            <li class="flex items-center gap-3 py-2">
              <span class="pill bg-raised text-muted">{{ roleLabel(inv.role) }}</span>
              <span class="flex-1 text-muted">Expires {{ date(inv.expires_at) }}</span>
              <button class="btn btn-ghost px-2 text-muted" (click)="revoke(inv)">Cancel link</button>
            </li>
          }
        </ul>
      }
    </section>
  }`,
})
export class TeamSettings {
  readonly auth = inject(AuthService);
  private api = inject(Api);
  private router = inject(Router);
  readonly roleInfo = ROLE_INFO;
  readonly roleLabel = roleLabel;
  readonly roles = ['admin', 'member', 'viewer'] as const;
  readonly members = signal<Member[]>([]);
  readonly invites = signal<Invite[]>([]);
  readonly fresh = signal<Invite | null>(null);
  readonly busy = signal(false);
  readonly copied = signal(false);
  readonly error = signal('');
  newRole: 'admin' | 'member' | 'viewer' = 'member';

  constructor() {
    effect(() => { this.auth.workspace(); untracked(() => this.load()); });
  }

  adminCount() { return this.members().filter((m) => m.role === 'admin').length; }
  date(iso: string) { return longDate(iso.slice(0, 10)); }
  private ws() { return this.auth.workspace()!.id; }

  async load() {
    if (!this.auth.workspace()) return;
    this.error.set(''); this.fresh.set(null);
    try {
      this.members.set(await this.api.get<Member[]>(`/workspaces/${this.ws()}/members`));
      this.invites.set(this.auth.isAdmin() ? await this.api.get<Invite[]>(`/workspaces/${this.ws()}/invites`) : []);
    } catch (e) { this.error.set(errorMessage(e)); }
  }

  async setRole(m: Member, role: string) {
    this.error.set('');
    try {
      await this.api.patch(`/workspaces/${this.ws()}/members/${m.user_id}`, { role });
      if (m.is_you) await this.auth.refresh();
    } catch (e) { this.error.set(errorMessage(e)); }
    await this.load();
  }

  async remove(m: Member) {
    if (!confirm(`Remove ${m.name} from ${this.auth.workspace()?.name}? They lose access straight away.`)) return;
    try { await this.api.delete(`/workspaces/${this.ws()}/members/${m.user_id}`); await this.load(); }
    catch (e) { this.error.set(errorMessage(e)); }
  }

  async leave(m: Member) {
    if (!confirm(`Leave ${this.auth.workspace()?.name}? You'll need a new invite to come back.`)) return;
    try {
      await this.api.delete(`/workspaces/${this.ws()}/members/${m.user_id}`);
      await this.auth.refresh();
      this.auth.selectWorkspace(this.auth.workspaces()[0]?.id ?? '');
      await this.router.navigateByUrl('/dashboard');
    } catch (e) { this.error.set(errorMessage(e)); }
  }

  async createInvite() {
    this.busy.set(true); this.error.set(''); this.copied.set(false);
    try {
      this.fresh.set(await this.api.post<Invite>(`/workspaces/${this.ws()}/invites`, { role: this.newRole }));
      this.invites.set(await this.api.get<Invite[]>(`/workspaces/${this.ws()}/invites`));
    } catch (e) { this.error.set(errorMessage(e)); }
    finally { this.busy.set(false); }
  }

  async revoke(inv: Invite) {
    try { await this.api.delete(`/workspaces/${this.ws()}/invites/${inv.id}`); await this.load(); }
    catch (e) { this.error.set(errorMessage(e)); }
  }

  async copy(url: string) {
    try { await navigator.clipboard.writeText(url); this.copied.set(true); } catch { /* the field is selectable */ }
  }
}
