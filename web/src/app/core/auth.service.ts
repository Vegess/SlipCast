import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Api } from './api.service';
import { API_URL } from './config';
import { User, Workspace } from './models';

const TOKEN_KEY = 'slipcast_token';
const WORKSPACE_KEY = 'slipcast_workspace';

interface TokenOut { access_token: string; user: User; }
interface MeOut { user: User; workspaces: Workspace[]; has_password: boolean; sign_in_methods: string[]; }
export type Provider = 'google' | 'github';

/** Only same-site paths, so links can't be used to send people to another site after sign-in. */
export function safeNext(path: string | null | undefined): string | null {
  return path && path.startsWith('/') && !path.startsWith('//') && !path.includes('\\') ? path : null;
}

function read(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}
function write(key: string, value: string | null) {
  try { value ? localStorage.setItem(key, value) : localStorage.removeItem(key); } catch { /* private mode */ }
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private api = inject(Api);
  private router = inject(Router);

  readonly user = signal<User | null>(null);
  readonly workspaces = signal<Workspace[]>([]);
  readonly hasPassword = signal(true);
  readonly signInMethods = signal<string[]>([]);
  private readonly selectedId = signal<string | null>(read(WORKSPACE_KEY));
  /** The workspace being viewed: the one last picked, or the first (the personal one). */
  readonly workspace = computed<Workspace | null>(() => {
    const all = this.workspaces();
    return all.find((w) => w.id === this.selectedId()) ?? all[0] ?? null;
  });
  readonly role = computed(() => this.workspace()?.role ?? 'viewer');
  /** Viewers can look at everything but change nothing; the API enforces this too. */
  readonly canEdit = computed(() => this.role() !== 'viewer');
  readonly isAdmin = computed(() => this.role() === 'admin');
  private loaded = false;
  private providerCache: Promise<Record<Provider, boolean>> | null = null;

  get token(): string | null { return read(TOKEN_KEY); }

  /** Resolves whether there is a valid session; called by the route guards. */
  async ensureLoaded(): Promise<boolean> {
    if (this.loaded) return this.user() !== null;
    this.loaded = true;
    if (!this.token) return false;
    try {
      await this.refresh();
      return true;
    } catch {
      write(TOKEN_KEY, null);
      return false;
    }
  }

  /** Re-reads the account, e.g. after joining a workspace. */
  async refresh() {
    const me = await this.api.get<MeOut>('/auth/me');
    this.user.set(me.user);
    this.workspaces.set(me.workspaces);
    this.hasPassword.set(me.has_password);
    this.signInMethods.set(me.sign_in_methods);
  }

  selectWorkspace(id: string) {
    this.selectedId.set(id);
    write(WORKSPACE_KEY, id);
  }

  /**
   * Which "Continue with…" buttons to show. A free-tier API can take a minute to wake up, so a
   * failed request is retried a few times and never remembered: the next visit asks again.
   */
  providers(): Promise<Record<Provider, boolean>> {
    this.providerCache ??= this.fetchProviders().catch(() => {
      this.providerCache = null;
      return { google: false, github: false };
    });
    return this.providerCache;
  }

  private async fetchProviders(attempt = 0): Promise<Record<Provider, boolean>> {
    try {
      return await this.api.get<Record<Provider, boolean>>('/auth/providers');
    } catch (e) {
      if (attempt >= 4) throw e;
      await new Promise((r) => setTimeout(r, 2000 * (attempt + 1)));  // 2, 4, 6, 8 s: about 20 s in all
      return this.fetchProviders(attempt + 1);
    }
  }

  /** Full-page navigation to the API, which runs the whole Google/GitHub sign-in on its side. */
  providerUrl(provider: Provider, next: string | null): string {
    const q = new URLSearchParams({ next: safeNext(next) ?? '/dashboard' });
    return `${API_URL}/auth/${provider}/start?${q}`;
  }

  async login(email: string, password: string) {
    const r = await this.api.post<TokenOut>('/auth/login', { email, password });
    await this.useToken(r.access_token);
  }

  async register(name: string, email: string, password: string) {
    const r = await this.api.post<TokenOut>('/auth/register', { name, email, password });
    await this.useToken(r.access_token);
  }

  async updateName(name: string) {
    const user = await this.api.patch<User>('/auth/me', { name });
    this.user.set(user);
  }

  /** Sets or changes the password. Other devices are signed out; this one keeps working. */
  async changePassword(currentPassword: string, newPassword: string) {
    const r = await this.api.post<TokenOut>('/auth/password', { current_password: currentPassword, new_password: newPassword });
    await this.useToken(r.access_token);
  }

  async logoutEverywhere() {
    await this.api.post('/auth/logout-all');
    this.logout();
  }

  /** Starts a session from a token (password sign-in, or the Google/GitHub callback). */
  async useToken(token: string) {
    write(TOKEN_KEY, token);
    this.loaded = false;
    await this.ensureLoaded();
  }

  logout() {
    write(TOKEN_KEY, null);
    this.user.set(null);
    this.workspaces.set([]);
    this.loaded = true;
    this.router.navigateByUrl('/login');
  }
}
