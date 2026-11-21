import { Injectable, computed, effect, inject, signal, untracked } from '@angular/core';
import { Api } from './api.service';
import { AuthService } from './auth.service';
import { Project } from './models';

const PRIVACY_KEY = 'slipcast_privacy';
function readPrivacy(): boolean {
  try { return localStorage.getItem(PRIVACY_KEY) === '1'; } catch { return false; }
}

@Injectable({ providedIn: 'root' })
export class WorkspaceStore {
  private api = inject(Api);
  private auth = inject(AuthService);

  readonly projects = signal<Project[]>([]);
  /** Privacy mode: no ticket titles or theme names go to the AI, and rewrites use the template. */
  readonly privacyMode = signal<boolean>(readPrivacy());

  setPrivacy(on: boolean) {
    this.privacyMode.set(on);
    try { localStorage.setItem(PRIVACY_KEY, on ? '1' : '0'); } catch { /* storage blocked */ }
  }
  readonly workspaceId = computed(() => this.auth.workspace()?.id ?? null);

  constructor() {
    // Switching workspace reloads its project list.
    effect(() => {
      const ws = this.workspaceId();
      untracked(() => { if (ws) this.load().catch(() => this.projects.set([])); else this.projects.set([]); });
    });
  }

  async load() {
    const ws = this.workspaceId();
    if (!ws) return;
    this.projects.set(await this.api.get<Project[]>(`/workspaces/${ws}/projects`));
  }
}
