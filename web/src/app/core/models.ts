export type Status = 'planned' | 'in_progress' | 'blocked' | 'done';
export type Priority = 'low' | 'medium' | 'high';
export type Kind = 'bug' | 'feature' | 'tech_debt' | 'support';

export interface User { id: string; email: string; name: string; }
export interface Workspace { id: string; name: string; role: string; }

export interface Project {
  id: string; workspace_id: string; name: string; goal: string; color: string;
  created_at: string; task_count: number; done_count: number;
  /** The module: software (Build), shipments (Ship) or services (Serve). */
  template?: Template;
}

export type Template = 'software' | 'shipments' | 'services';
/** What one promise is called in each module. */
export const NOUN: Record<Template, { one: string; many: string }> = {
  software: { one: 'ticket', many: 'tickets' },
  shipments: { one: 'order', many: 'orders' },
  services: { one: 'job', many: 'jobs' },
};

export interface Task {
  id: string; project_id: string; title: string; owner: string; status: Status;
  priority: Priority; due: string | null; notes: string; description: string;
  kind: Kind | null; kind_source: string; started_at: string | null; completed_at: string | null;
  position: number; created_at: string; updated_at: string;
  stage?: string | null; item_type?: string; attributes?: Record<string, unknown> | null;
}

export interface Finding { id: string; kind: string; severity: 'info' | 'warning' | 'critical'; text: string; }
export interface Suggestion {
  key: string; title: string; action: string; finding_ids: string[];
  impact: 'high' | 'medium' | 'low'; source: 'llm' | 'rules';
}

/** Colours follow the active theme (Dusk values: #A3AEC4, #6EA8FE, #FF7A7A, #4FD1A5). */
export const STATUSES: { id: Status; label: string; color: string }[] = [
  { id: 'planned', label: 'Planned', color: 'rgb(var(--c-muted))' },
  { id: 'in_progress', label: 'In progress', color: 'rgb(var(--c-info))' },
  { id: 'blocked', label: 'Blocked', color: 'rgb(var(--c-bad))' },
  { id: 'done', label: 'Done', color: 'rgb(var(--c-ok))' },
];

export const KIND_LABEL: Record<string, string | undefined> = {
  bug: 'Bug', feature: 'Feature', tech_debt: 'Tech debt', support: 'Support', unknown: 'Unknown',
};

export interface ReferenceClass {
  available: boolean; reason: string; n: number; summary?: string;
  p10?: number; p25?: number; p50?: number; p85?: number; p90?: number; late_rate?: number | null;
  similar: { id: string; title: string; days: number; similarity: number }[];
  plan?: { planned_days: number | null; under_planned: boolean; message: string } | null;
  actual_days?: number;
}

export interface TicketCheck {
  quality: { score: number; reasons: string[] };
  reference: ReferenceClass;
  slip_risk: { risk: number; factors: string[] } | null;
  duplicates: { id: string; title: string; status: string; similarity: number }[];
}
