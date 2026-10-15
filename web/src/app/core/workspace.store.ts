import { Injectable, computed, inject, signal } from '@angular/core';
import { Api } from './api.service';
import { AuthService } from './auth.service';
import { Project } from './models';

@Injectable({ providedIn: 'root' })
export class WorkspaceStore {
  private api = inject(Api);
  private auth = inject(AuthService);

  readonly projects = signal<Project[]>([]);
  readonly workspaceId = computed(() => this.auth.workspace()?.id ?? null);

  async load() {
    const ws = this.workspaceId();
    if (!ws) return;
    this.projects.set(await this.api.get<Project[]>(`/workspaces/${ws}/projects`));
  }
}
