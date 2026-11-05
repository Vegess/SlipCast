import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Api } from './api.service';
import { User, Workspace } from './models';

const TOKEN_KEY = 'slipcast_token';

interface TokenOut { access_token: string; user: User; }
interface MeOut { user: User; workspaces: Workspace[]; }

@Injectable({ providedIn: 'root' })
export class AuthService {
  private api = inject(Api);
  private router = inject(Router);

  readonly user = signal<User | null>(null);
  readonly workspaces = signal<Workspace[]>([]);
  readonly workspace = computed<Workspace | null>(() => this.workspaces()[0] ?? null);
  private loaded = false;

  get token(): string | null {
    try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
  }
  private setToken(token: string | null) {
    try { token ? localStorage.setItem(TOKEN_KEY, token) : localStorage.removeItem(TOKEN_KEY); } catch { /* private mode */ }
  }

  /** Resolves whether there is a valid session; called by the route guards. */
  async ensureLoaded(): Promise<boolean> {
    if (this.loaded) return this.user() !== null;
    this.loaded = true;
    if (!this.token) return false;
    try {
      const me = await this.api.get<MeOut>('/auth/me');
      this.user.set(me.user);
      this.workspaces.set(me.workspaces);
      return true;
    } catch {
      this.setToken(null);
      return false;
    }
  }

  async login(email: string, password: string) {
    const r = await this.api.post<TokenOut>('/auth/login', { email, password });
    await this.start(r.access_token);
  }

  async register(name: string, email: string, password: string) {
    const r = await this.api.post<TokenOut>('/auth/register', { name, email, password });
    await this.start(r.access_token);
  }

  private async start(token: string) {
    this.setToken(token);
    this.loaded = false;
    await this.ensureLoaded();
    await this.router.navigateByUrl('/');
  }

  logout() {
    this.setToken(null);
    this.user.set(null);
    this.workspaces.set([]);
    this.loaded = true;
    this.router.navigateByUrl('/login');
  }
}
