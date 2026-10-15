import { Injectable, inject, signal } from '@angular/core';
import { Api } from '../../core/api.service';
import { Project, Task } from '../../core/models';
import { WorkspaceStore } from '../../core/workspace.store';

/** State for the open project, shared by its tab views. Provided by ProjectPage. */
@Injectable()
export class ProjectContext {
  private api = inject(Api);
  private store = inject(WorkspaceStore);

  readonly id = signal<string>('');
  readonly project = signal<Project | null>(null);
  readonly tasks = signal<Task[]>([]);
  /** Bumped after any change so analytics views refetch. */
  readonly version = signal(0);

  async select(id: string) {
    this.id.set(id);
    this.project.set(null);
    this.tasks.set([]);
    const [project, tasks] = await Promise.all([
      this.api.get<Project>(`/projects/${id}`),
      this.api.get<Task[]>(`/projects/${id}/tasks`),
    ]);
    if (this.id() !== id) return;
    this.project.set(project);
    this.tasks.set(tasks);
  }

  private touched() {
    this.version.update((v) => v + 1);
    this.api.get<Project>(`/projects/${this.id()}`).then((p) => this.project.set(p)).catch(() => {});
    this.store.load().catch(() => {});
  }

  async createTask(body: Partial<Task>) {
    const t = await this.api.post<Task>(`/projects/${this.id()}/tasks`, body);
    this.tasks.update((ts) => [...ts, t]);
    this.touched();
  }

  async updateTask(id: string, patch: Partial<Task>) {
    const before = this.tasks();
    this.tasks.update((ts) => ts.map((t) => (t.id === id ? { ...t, ...patch } : t)));
    try {
      const t = await this.api.patch<Task>(`/tasks/${id}`, patch);
      this.tasks.update((ts) => ts.map((x) => (x.id === id ? t : x)));
      this.touched();
    } catch (e) {
      this.tasks.set(before);
      throw e;
    }
  }

  async deleteTask(id: string) {
    await this.api.delete(`/tasks/${id}`);
    this.tasks.update((ts) => ts.filter((t) => t.id !== id));
    this.touched();
  }

  async rename(name: string) {
    const p = await this.api.patch<Project>(`/projects/${this.id()}`, { name });
    this.project.set(p);
    this.store.load();
  }

  async remove() {
    await this.api.delete(`/projects/${this.id()}`);
    await this.store.load();
  }
}
