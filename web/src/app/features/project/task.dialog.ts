import { Component, OnDestroy, OnInit, computed, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Api, errorMessage } from '../../core/api.service';
import { KIND_LABEL, STATUSES, Task, TicketCheck } from '../../core/models';
import { ModalComponent } from '../../shared/modal.component';
import { WorkspaceStore } from '../../core/workspace.store';
import { ProjectContext } from './project.context';
import { AuthService } from '../../core/auth.service';

interface OrderEstimate {
  available: boolean; reason?: string; basis: string; n: number; p10: number; p50: number; p90: number;
  planned_days: number | null; late_share: number | null; under_planned?: boolean;
  carriers_on_route: { carrier: string; on_time_rate: number; delivered: number }[];
}

interface JobCheck {
  available: boolean; reason?: string; estimate_short?: boolean;
  duration: { basis: string; n: number; p10: number; p50: number; p90: number } | null;
  miss_risk: { risk: number; jobs_that_day: number; reasons: string[] } | null;
  technicians: { tech: string; on_time_rate: number; jobs_that_day: number | null }[];
}

@Component({
  selector: 'app-task-dialog',
  imports: [FormsModule, ModalComponent],
  template: `
  <app-modal [heading]="heading()" [wide]="true" (closed)="closed.emit()">
    <div class="grid gap-6 sm:grid-cols-[minmax(0,1fr)_260px]">
      <form id="task-form" class="grid content-start gap-4" (ngSubmit)="save()" (input)="schedule()" (change)="schedule()">
        <label class="label">Title <input class="input" name="title" [(ngModel)]="form.title" maxlength="140" required></label>
        <label class="label">Description <textarea class="input min-h-[120px]" name="description" [(ngModel)]="form.description" maxlength="5000"></textarea></label>
        @if (isJob) {
          <div class="grid gap-4 sm:grid-cols-2">
            <label class="label">Service <input class="input" name="service_type" [(ngModel)]="job.service_type" maxlength="60" list="serve-services" placeholder="e.g. AC repair"></label>
            <label class="label">Area <input class="input" name="area" [(ngModel)]="job.area" maxlength="60" list="serve-areas" placeholder="e.g. Indiranagar"></label>
            <label class="label">Technician <input class="input" name="technician" [(ngModel)]="job.technician" maxlength="40" list="serve-techs"></label>
            <label class="label">Booked for (hours) <input class="input" type="number" min="0" max="48" step="0.25" name="estimate" [(ngModel)]="job.estimate_hours"></label>
            <label class="label">Appointment date <input class="input" type="date" name="due" [(ngModel)]="form.due"></label>
            <div class="grid grid-cols-2 gap-2">
              <label class="label">From <input class="input" type="time" name="from" [(ngModel)]="job.from"></label>
              <label class="label">To <input class="input" type="time" name="to" [(ngModel)]="job.to"></label>
            </div>
            <label class="label">Stage
              <select class="input" name="jstage" [(ngModel)]="job.stage">@for (s of jobStages; track s[0]) { <option [value]="s[0]">{{ s[1] }}</option> }</select>
            </label>
          </div>
          <datalist id="serve-services">@for (x of distinctOf(['service_type']); track x) { <option [value]="x"></option> }</datalist>
          <datalist id="serve-areas">@for (x of distinctOf(['area']); track x) { <option [value]="x"></option> }</datalist>
          <datalist id="serve-techs">@for (x of distinctOf(['technician']); track x) { <option [value]="x"></option> }</datalist>
        } @else if (isOrder) {
          <div class="grid gap-4 sm:grid-cols-2">
            <label class="label">From (warehouse) <input class="input" name="origin" [(ngModel)]="order.origin" maxlength="60" list="ship-places" placeholder="e.g. Chennai"></label>
            <label class="label">To <input class="input" name="destination" [(ngModel)]="order.destination" maxlength="60" list="ship-places" placeholder="e.g. Delhi"></label>
            <label class="label">Carrier <input class="input" name="carrier" [(ngModel)]="order.carrier" maxlength="40" list="ship-carriers"></label>
            <label class="label">Service
              <select class="input" name="service" [(ngModel)]="order.service"><option value="standard">Standard</option><option value="express">Express</option></select>
            </label>
            <label class="label">Promised delivery date <input class="input" type="date" name="due" [(ngModel)]="form.due"></label>
            <label class="label">Stage
              <select class="input" name="stage" [(ngModel)]="order.stage">@for (s of shipStages; track s[0]) { <option [value]="s[0]">{{ s[1] }}</option> }</select>
            </label>
            <label class="label">Weight (kg) <input class="input" type="number" min="0" step="0.1" name="weight" [(ngModel)]="order.weight_kg"></label>
            <label class="label">Order value <input class="input" type="number" min="0" step="1" name="value" [(ngModel)]="order.order_value"></label>
          </div>
          <datalist id="ship-places">@for (x of places(); track x) { <option [value]="x"></option> }</datalist>
          <datalist id="ship-carriers">@for (x of carriers(); track x) { <option [value]="x"></option> }</datalist>
        } @else {
        <div class="grid gap-4 sm:grid-cols-2">
          <label class="label">Owner <input class="input" name="owner" [(ngModel)]="form.owner" maxlength="40"></label>
          <label class="label">Due date <input class="input" type="date" name="due" [(ngModel)]="form.due"></label>
          <label class="label">Status
            <select class="input" name="status" [(ngModel)]="form.status">@for (s of statuses; track s.id) { <option [value]="s.id">{{ s.label }}</option> }</select>
          </label>
          <label class="label">Priority
            <select class="input" name="priority" [(ngModel)]="form.priority"><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select>
          </label>
          <label class="label">Type
            <select class="input" name="kind" [(ngModel)]="form.kind">
              <option [ngValue]="null">Not set</option>
              @for (k of kinds; track k) { <option [value]="k">{{ kindLabel[k] }}</option> }
            </select>
          </label>
        </div>
        }
        @if (error()) { <p class="text-sm text-bad">{{ error() }}</p> }
      </form>

      @if (isJob) {
      <aside class="flex min-w-0 flex-col gap-4 self-start rounded-xl border border-line border-t-2 border-t-violet/80 bg-canvas/60 p-4 text-sm" aria-live="polite" aria-label="Job check">
        <div>
          <p class="text-xs font-medium uppercase tracking-wide text-muted">Job check</p>
          <p class="mt-1 text-xs text-muted">From this project's past visits, as you fill in the booking. It never blocks saving.</p>
        </div>
        @if (jobCheck(); as c) {
          @if (c.available) {
            @if (c.duration; as d) {
              <div>
                <p class="text-xs font-medium text-muted">Jobs like this took</p>
                <p class="mt-1 font-display text-2xl">{{ d.p10 }}–{{ d.p90 }} <span class="text-sm text-muted">hours</span></p>
                <p class="text-xs text-muted">Typical {{ d.p50 }} h · {{ d.n }} {{ d.basis }}</p>
                @if (c.estimate_short) { <p class="mt-1 text-xs text-bad">Booked for {{ job.estimate_hours }} h: shorter than 3 in 4 of them took.</p> }
              </div>
            }
            @if (c.miss_risk; as r) {
              <div>
                <p class="text-xs font-medium text-muted">Chance the visit is missed</p>
                <p class="mt-1 font-display text-2xl" [class.text-bad]="r.risk >= .5" [class.text-accent]="r.risk >= .25 && r.risk < .5" [class.text-ok]="r.risk < .25">{{ (r.risk * 100).toFixed(0) }}%</p>
                <p class="text-xs text-muted">Late arrival or a reschedule. {{ job.technician }} would have {{ r.jobs_that_day }} job{{ r.jobs_that_day === 1 ? '' : 's' }} that day.</p>
                @if (r.reasons.length) { <ul class="mt-1 list-disc space-y-0.5 pl-4 text-xs text-muted">@for (x of r.reasons; track x) { <li>{{ x }}</li> }</ul> }
              </div>
            }
          } @else { <p class="text-xs text-muted">{{ c.reason }}</p> }
          @if (c.technicians.length > 1) {
            <div>
              <p class="text-xs font-medium text-muted">Who else does this{{ form.due ? ', and how busy they are that day' : '' }}</p>
              <ul class="mt-1.5 space-y-1 text-xs">
                @for (t of c.technicians.slice(0, 5); track t.tech) {
                  <li class="flex items-center gap-2"><span class="w-20 truncate" [class.font-semibold]="t.tech === job.technician">{{ t.tech }}</span>
                    <span class="flex-1 text-muted">{{ (t.on_time_rate * 100).toFixed(0) }}% on time</span>
                    @if (t.jobs_that_day !== null) { <span [class.text-bad]="t.jobs_that_day >= 3" [class.text-muted]="t.jobs_that_day < 3">{{ t.jobs_that_day }} booked</span> }</li>
                }
              </ul>
            </div>
          }
        } @else { <p class="text-xs text-muted">{{ checkError() || 'Add the service and technician.' }}</p> }
      </aside>
      } @else if (isOrder) {
      <aside class="flex min-w-0 flex-col gap-4 self-start rounded-xl border border-line border-t-2 border-t-violet/80 bg-canvas/60 p-4 text-sm" aria-live="polite" aria-label="Order check">
        <div>
          <p class="text-xs font-medium uppercase tracking-wide text-muted">Order check</p>
          <p class="mt-1 text-xs text-muted">How long orders like this really took, from this project's deliveries. It never blocks saving.</p>
        </div>
        @if (estimate(); as e) {
          @if (e.available) {
            <div>
              <p class="text-xs font-medium text-muted">Orders like this took</p>
              <p class="mt-1 font-display text-2xl">{{ e.p10 }}–{{ e.p90 }} <span class="text-sm text-muted">days</span></p>
              <p class="text-xs text-muted">Typical {{ e.p50 }} days · {{ e.n }} {{ e.basis }}</p>
            </div>
            @if (e.planned_days !== null) {
              <div>
                <p class="text-xs font-medium text-muted">Against your promise of {{ e.planned_days }} day{{ e.planned_days === 1 ? '' : 's' }}</p>
                <p class="mt-1 font-display text-2xl" [class.text-bad]="(e.late_share ?? 0) >= .6" [class.text-accent]="(e.late_share ?? 0) >= .3 && (e.late_share ?? 0) < .6" [class.text-ok]="(e.late_share ?? 0) < .3">{{ ((e.late_share ?? 0) * 100).toFixed(0) }}%</p>
                <p class="text-xs text-muted">of them would have arrived after that date.@if (e.under_planned) { <span class="text-bad"> The promise is shorter than 3 in 4 of them took.</span> }</p>
              </div>
            }
            @if (e.carriers_on_route.length > 1) {
              <div>
                <p class="text-xs font-medium text-muted">On time on this route, by carrier</p>
                <ul class="mt-1.5 space-y-1 text-xs">
                  @for (c of e.carriers_on_route; track c.carrier) {
                    <li class="flex items-center gap-2"><span class="w-24 truncate" [class.font-semibold]="c.carrier === order.carrier">{{ c.carrier }}</span>
                      <span class="h-1.5 flex-1 overflow-hidden rounded bg-line"><span class="block h-full rounded bg-ok/80" [style.width.%]="c.on_time_rate * 100"></span></span>
                      <span class="w-9 text-right text-muted">{{ (c.on_time_rate * 100).toFixed(0) }}%</span></li>
                  }
                </ul>
              </div>
            }
          } @else { <p class="text-xs text-muted">{{ e.reason }}</p> }
        } @else { <p class="text-xs text-muted">{{ checkError() || 'Add where it ships from and to.' }}</p> }
      </aside>
      } @else {
      <aside class="flex min-w-0 flex-col gap-4 self-start rounded-xl border border-line border-t-2 border-t-violet/80 bg-canvas/60 p-4 text-sm" aria-live="polite" aria-label="Ticket check">
        <div>
          <p class="text-xs font-medium uppercase tracking-wide text-muted">Ticket check</p>
          <p class="mt-1 text-xs text-muted">Compared with this project's history as you type. It never blocks saving.</p>
        </div>
        @if (check(); as c) {
          <div>
            <p class="flex items-baseline gap-2"><span class="font-display text-3xl" [class.text-bad]="c.quality.score < 50" [class.text-accent]="c.quality.score >= 50 && c.quality.score < 80" [class.text-ok]="c.quality.score >= 80">{{ c.quality.score }}</span><span class="text-muted">/100 ready to work on</span></p>
            @if (c.quality.reasons.length) {
              <ul class="mt-1.5 list-disc space-y-0.5 pl-4 text-xs text-muted">@for (r of c.quality.reasons; track r) { <li>{{ r }}</li> }</ul>
            }
          </div>
          <div>
            <p class="text-xs font-medium text-muted">How long tickets like this really took</p>
            @if (c.reference.available) {
              <p class="mt-1 font-medium">{{ c.reference.summary }}</p>
              @if (c.reference.plan?.planned_days !== null && c.reference.plan) {
                <p class="mt-1 text-xs" [class.text-bad]="c.reference.plan.under_planned" [class.text-muted]="!c.reference.plan.under_planned">{{ c.reference.plan.message }}</p>
              }
              <ul class="mt-2 space-y-1 text-xs text-muted">
                @for (s of c.reference.similar; track s.id) { <li class="flex gap-2"><span class="w-10 shrink-0 text-fg">{{ s.days }}d</span><span class="truncate" [title]="s.title">{{ s.title }}</span></li> }
              </ul>
            } @else { <p class="mt-1 text-xs text-muted">{{ c.reference.reason }}</p> }
          </div>
          @if (c.slip_risk) {
            <div>
              <p class="text-xs font-medium text-muted">Chance of missing the due date</p>
              <p class="mt-1 font-display text-2xl" [class.text-bad]="c.slip_risk.risk >= .6" [class.text-accent]="c.slip_risk.risk >= .35 && c.slip_risk.risk < .6" [class.text-ok]="c.slip_risk.risk < .35">{{ (c.slip_risk.risk * 100).toFixed(0) }}%</p>
              @if (c.slip_risk.factors.length) { <p class="text-xs text-muted">{{ c.slip_risk.factors.join(' · ') }}</p> }
            </div>
          }
          <div>
            <button type="button" class="btn w-full text-xs" (click)="suggestRewrite()" [disabled]="rewriting()">{{ rewriting() ? 'Writing…' : 'Suggest a clearer version' }}</button>
            @if (rewrite(); as r) {
              <div class="mt-2 rounded-lg border border-line p-2.5 text-xs">
                <p class="font-medium text-fg">{{ r.title }}</p>
                <p class="mt-1 max-h-32 overflow-y-auto whitespace-pre-line text-muted">{{ r.description }}</p>
                <p class="mt-1 text-muted">{{ r.provider === 'groq' ? 'Written by the AI. Check it before using.' : 'Template: fill in the [brackets].' }}</p>
                <button type="button" class="btn mt-2 px-2 py-1 text-xs" (click)="useRewrite()">Use this</button>
              </div>
            }
          </div>
          @if (c.duplicates.length) {
            <div>
              <p class="text-xs font-medium text-accent">Possible duplicates</p>
              <ul class="mt-1 space-y-1 text-xs">@for (d of c.duplicates; track d.id) { <li>{{ (d.similarity * 100).toFixed(0) }}% · {{ d.title }} <span class="text-muted">({{ d.status }})</span></li> }</ul>
            </div>
          }
        } @else { <p class="text-xs text-muted">{{ checkError() || 'Start typing to check this ticket.' }}</p> }
      </aside>
      }
    </div>

    <ng-container footer>
      @if (auth.canEdit()) {
        @if (task()) { <button class="btn btn-ghost mr-auto text-bad" (click)="remove()">Delete</button> }
        <button class="btn" (click)="closed.emit()">Cancel</button>
        <button class="btn btn-primary" form="task-form" [disabled]="saving()">{{ saving() ? 'Saving…' : 'Save' }}</button>
      } @else {
        <span class="mr-auto text-xs text-muted">View only: changes can't be saved.</span>
        <button class="btn" (click)="closed.emit()">Close</button>
      }
    </ng-container>
  </app-modal>`,
})
export class TaskDialog implements OnInit, OnDestroy {
  private ctx = inject(ProjectContext);
  /** Ship projects edit orders: route, carrier, service and stage instead of owner and type. */
  readonly isOrder = this.ctx.template() === 'shipments';
  /** Serve projects edit jobs: service, area, technician, appointment window and booked hours. */
  readonly isJob = this.ctx.template() === 'services';
  readonly jobStages = [['booked', 'Booked'], ['scheduled', 'Scheduled'], ['assigned', 'Assigned'], ['en_route', 'En route'],
    ['on_site', 'On site'], ['done', 'Done'], ['rescheduled', 'Rescheduled'], ['cancelled', 'Cancelled']];
  job = { service_type: '', area: '', technician: '', estimate_hours: null as number | null, from: '10:00', to: '12:00', stage: 'booked' };
  readonly jobCheck = signal<JobCheck | null>(null);
  distinctOf(keys: string[]) { return this.distinct(keys); }
  /** The appointment window as UTC ISO strings, from the local date and times typed in. */
  private windowISO(): [string | null, string | null] {
    if (!this.form.due) return [null, null];
    const at = (t: string) => { const d = new Date(`${this.form.due}T${t || '00:00'}`); return isNaN(d.getTime()) ? null : d.toISOString(); };
    return [at(this.job.from), at(this.job.to)];
  }
  readonly shipStages = [['ordered', 'Ordered'], ['packed', 'Packed'], ['dispatched', 'Dispatched'], ['in_transit', 'In transit'],
    ['out_for_delivery', 'Out for delivery'], ['exception', 'Exception'], ['delivered', 'Delivered']];
  order = { origin: '', destination: '', carrier: '', service: 'standard', stage: 'ordered', weight_kg: null as number | null, order_value: null as number | null };
  readonly estimate = signal<OrderEstimate | null>(null);
  /** Places and carriers already used in this project, offered as suggestions. */
  readonly places = computed(() => this.distinct(['origin', 'destination']));
  readonly carriers = computed(() => this.distinct(['carrier']));
  private distinct(keys: string[]) {
    const out = new Set<string>();
    for (const t of this.ctx.tasks()) for (const k of keys) { const v = t.attributes?.[k]; if (typeof v === 'string' && v) out.add(v); }
    return [...out].sort();
  }
  heading() {
    const one = this.ctx.noun().one, title = one.charAt(0).toUpperCase() + one.slice(1);
    return this.task() ? (this.auth.canEdit() ? title : `${title} (view only)`) : `New ${one}`;
  }
  readonly auth = inject(AuthService);
  private api = inject(Api);
  private timer: ReturnType<typeof setTimeout> | undefined;
  private seq = 0;
  readonly check = signal<TicketCheck | null>(null);
  readonly checkError = signal('');
  private store = inject(WorkspaceStore);
  readonly rewrite = signal<{ title: string; description: string; provider: string } | null>(null);
  readonly rewriting = signal(false);

  async suggestRewrite() {
    this.rewriting.set(true);
    try {
      this.rewrite.set(await this.api.post(`/projects/${this.ctx.id()}/rewrite`, {
        title: this.form.title, description: this.form.description, kind: this.form.kind || null, privacy_mode: this.store.privacyMode(),
      }));
    } catch (e) { this.checkError.set(errorMessage(e)); }
    finally { this.rewriting.set(false); }
  }

  useRewrite() {
    const r = this.rewrite();
    if (!r) return;
    this.form = { ...this.form, title: r.title, description: r.description };
    this.rewrite.set(null);
    this.schedule();
  }
  readonly task = input<Task | null>(null);
  readonly closed = output<void>();
  readonly statuses = STATUSES;
  readonly kinds = ['bug', 'feature', 'tech_debt', 'support'];
  readonly kindLabel = KIND_LABEL;
  readonly saving = signal(false);
  readonly error = signal('');
  form = { title: '', description: '', owner: '', due: '', status: 'planned', priority: 'medium', kind: null as string | null };

  ngOnInit() {
    const t = this.task();
    if (t) {
      this.form = { title: t.title, description: t.description, owner: t.owner, due: t.due ?? '', status: t.status,
        priority: t.priority, kind: t.kind_source === 'label' ? t.kind : null };
      const a = t.attributes ?? {};
      const str = (k: string) => (typeof a[k] === 'string' ? (a[k] as string) : '');
      const num = (k: string) => (typeof a[k] === 'number' ? (a[k] as number) : null);
      const local = (iso: string) => { const d = new Date(iso); return isNaN(d.getTime()) ? '' : d.toTimeString().slice(0, 5); };
      this.job = { service_type: str('service_type'), area: str('area'), technician: str('technician') || t.owner,
        estimate_hours: num('estimate_hours'), from: str('window_start') ? local(str('window_start')) : '10:00',
        to: str('window_end') ? local(str('window_end')) : '12:00', stage: t.stage || 'booked' };
      if (this.isJob && str('window_start')) {
        const d = new Date(str('window_start'));
        if (!isNaN(d.getTime())) this.form.due = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
      }
      this.order = { origin: str('origin'), destination: str('destination'), carrier: str('carrier') || t.owner,
        service: str('service') || 'standard', stage: t.stage || 'ordered', weight_kg: num('weight_kg'), order_value: num('order_value') };
    }
    this.runCheck();
  }

  ngOnDestroy() { clearTimeout(this.timer); this.seq++; }

  /** Debounced write-time check: waits 600 ms after the last keystroke. */
  schedule() {
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.runCheck(), 600);
  }

  private async runCheck() {
    const seq = ++this.seq;
    const f = this.form;
    if (this.isJob) {
      const j = this.job;
      if (!j.service_type.trim() && !j.technician.trim()) { this.jobCheck.set(null); return; }
      try {
        const r = await this.api.post<JobCheck>(`/projects/${this.ctx.id()}/serve/estimate`, {
          service_type: j.service_type, area: j.area, technician: j.technician, window_start: this.windowISO()[0],
          estimate_hours: j.estimate_hours,
        });
        if (seq === this.seq) { this.jobCheck.set(r); this.checkError.set(''); }
      } catch (e) { if (seq === this.seq) this.checkError.set(errorMessage(e)); }
      return;
    }
    if (this.isOrder) {
      const o = this.order;
      if (!o.destination.trim() && !o.carrier.trim()) { this.estimate.set(null); return; }
      try {
        const r = await this.api.post<OrderEstimate>(`/projects/${this.ctx.id()}/ship/estimate`, {
          origin: o.origin, destination: o.destination, carrier: o.carrier, service: o.service, due: f.due || null,
        });
        if (seq === this.seq) { this.estimate.set(r); this.checkError.set(''); }
      } catch (e) { if (seq === this.seq) this.checkError.set(errorMessage(e)); }
      return;
    }
    try {
      const r = await this.api.post<TicketCheck>(`/projects/${this.ctx.id()}/ticket-check`, {
        title: f.title, description: f.description, owner: f.owner, due: f.due || null, priority: f.priority,
        kind: f.kind || null, task_id: this.task()?.id ?? null,
      });
      if (seq === this.seq) { this.check.set(r); this.checkError.set(''); }
    } catch (e) {
      if (seq === this.seq) this.checkError.set(errorMessage(e));
    }
  }

  async save() {
    if (!this.auth.canEdit()) return;
    if (!this.form.title.trim()) { this.error.set(`Add a title to save the ${this.ctx.noun().one}.`); return; }
    this.saving.set(true);
    const body: Record<string, unknown> = { ...this.form, due: this.form.due || null };
    if (!body['kind']) delete body['kind'];
    if (this.isJob) {
      const j = this.job, prev = this.task()?.attributes ?? {};
      const [start, end] = this.windowISO();
      const attributes: Record<string, unknown> = { ...prev, service_type: j.service_type.trim(), area: j.area.trim(),
        technician: j.technician.trim(), window_start: start, window_end: end };
      if (j.estimate_hours !== null) attributes['estimate_hours'] = j.estimate_hours;
      Object.assign(body, { owner: j.technician.trim(), attributes });
      delete body['status'];
      if (j.stage !== (this.task()?.stage ?? '')) body['stage'] = j.stage;
      if (!this.task()) body['item_type'] = 'job';
    }
    if (this.isOrder) {
      const o = this.order, prev = this.task()?.attributes ?? {};
      const attributes: Record<string, unknown> = { ...prev, origin: o.origin.trim(), destination: o.destination.trim(),
        carrier: o.carrier.trim(), service: o.service };
      if (o.weight_kg !== null) attributes['weight_kg'] = o.weight_kg;
      if (o.order_value !== null) attributes['order_value'] = o.order_value;
      Object.assign(body, { owner: o.carrier.trim(), priority: o.service === 'express' ? 'high' : 'medium', attributes });
      delete body['status'];
      if (o.stage !== (this.task()?.stage ?? '')) body['stage'] = o.stage;
      if (!this.task()) body['item_type'] = 'order';
    }
    try {
      const t = this.task();
      if (t) await this.ctx.updateTask(t.id, body as Partial<Task>);
      else await this.ctx.createTask(body as Partial<Task>);
      this.closed.emit();
    } catch (e) {
      this.error.set(errorMessage(e));
      this.saving.set(false);
    }
  }

  async remove() {
    try { await this.ctx.deleteTask(this.task()!.id); this.closed.emit(); }
    catch (e) { this.error.set(errorMessage(e)); }
  }
}
