import { Injectable, OnDestroy, computed, inject, signal } from '@angular/core';
import { Alert, AlertsService } from '../../core/alerts.service';
import { Api } from '../../core/api.service';
import { API_URL } from '../../core/config';
import { NOUN, Project, Task } from '../../core/models';
import { WorkspaceStore } from '../../core/workspace.store';

/** State for the open project, shared by its tab views. Provided by ProjectPage. */
@Injectable()
export class ProjectContext implements OnDestroy {
  private api = inject(Api);
  private store = inject(WorkspaceStore);
  private alerts = inject(AlertsService);

  /** Live connection state, shown as the "Live" dot in the project header. */
  readonly live = signal<'off' | 'connecting' | 'live'>('off');
  /** Tickets that just changed from somewhere else; the board makes them glow briefly. */
  readonly flashed = signal<ReadonlySet<string>>(new Set());
  /** What arrived live during this visit, newest first (the Live feed tab shows it). */
  readonly activity = signal<{ at: Date; kind: 'change' | 'alert'; text: string }[]>([]);
  private source: EventSource | null = null;
  private retries = 0;
  private timers: ReturnType<typeof setTimeout>[] = [];
  private pending = new Set<string>();
  private pendingFrom = new Set<string>();
  private refreshTimer: ReturnType<typeof setTimeout> | null = null;

  readonly id = signal<string>('');
  readonly project = signal<Project | null>(null);
  readonly tasks = signal<Task[]>([]);
  /** The project's module and what its items are called ("ticket", "order"). */
  readonly template = computed(() => this.project()?.template ?? 'software');
  readonly noun = computed(() => NOUN[this.template()]);
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
    this.connect();
  }

  // ---------- live updates ----------

  /** Opens the live stream. It closes itself every few minutes by design; we reconnect. */
  async connect() {
    this.disconnect();
    const id = this.id();
    if (!id || typeof EventSource === 'undefined') return;
    this.live.set('connecting');
    let token: string;
    try {
      token = (await this.api.post<{ token: string }>(`/projects/${id}/stream-token`)).token;
    } catch { this.reconnectLater(); return; }
    if (this.id() !== id) return;
    const es = new EventSource(`${API_URL}/projects/${id}/stream?token=${encodeURIComponent(token)}`);
    this.source = es;
    es.addEventListener('ready', () => { this.live.set('live'); this.retries = 0; });
    es.addEventListener('change', (e) => this.onChange(JSON.parse((e as MessageEvent).data)));
    es.addEventListener('alert', (e) => {
      const alert = JSON.parse((e as MessageEvent).data).alert as Alert;
      this.alerts.push(alert);
      this.log('alert', alert.message);
    });
    es.onerror = () => { if (this.source === es) { es.close(); this.source = null; this.reconnectLater(); } };
  }

  private reconnectLater() {
    this.live.set('connecting');
    const delay = Math.min(30_000, 1000 * 2 ** this.retries++);
    this.timers.push(setTimeout(() => this.connect(), delay));
  }

  private disconnect() {
    this.source?.close();
    this.source = null;
    this.timers.forEach(clearTimeout);
    this.timers = [];
  }

  /** Many events can arrive at once; gather them for a moment, then refresh once. */
  private onChange(msg: { task_ids: string[]; source: string; deleted?: boolean }) {
    if (!msg.deleted) msg.task_ids.forEach((t) => this.pending.add(t));
    this.pendingFrom.add(msg.source);
    if (this.refreshTimer) return;
    this.refreshTimer = setTimeout(() => this.applyLive(), 250);
  }

  private async applyLive() {
    this.refreshTimer = null;
    const ids = new Set(this.pending), from = [...this.pendingFrom];
    this.pending.clear(); this.pendingFrom.clear();
    const id = this.id();
    try {
      const tasks = await this.api.get<Task[]>(`/projects/${id}/tasks`);
      if (this.id() !== id) return;
      this.tasks.set(tasks);
    } catch { return; }
    this.flashed.set(ids);
    this.timers.push(setTimeout(() => this.flashed.set(new Set()), 2300));
    this.touched();
    const n = ids.size;
    this.log('change', from.includes('events')
      ? `${n} item${n === 1 ? '' : 's'} updated from another system`
      : `${n || 'An'} item${n === 1 ? '' : 's'} changed by someone in the app`);
  }

  private log(kind: 'change' | 'alert', text: string) {
    this.activity.update((a) => [{ at: new Date(), kind, text }, ...a].slice(0, 20));
  }

  ngOnDestroy() {
    this.disconnect();
    if (this.refreshTimer) clearTimeout(this.refreshTimer);
    this.live.set('off');
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
