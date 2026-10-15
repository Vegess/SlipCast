export type Status = 'planned' | 'in_progress' | 'blocked' | 'done';
export type Priority = 'low' | 'medium' | 'high';
export type Kind = 'bug' | 'feature' | 'tech_debt' | 'support';

export interface User { id: string; email: string; name: string; }
export interface Workspace { id: string; name: string; role: string; }

export interface Project {
  id: string; workspace_id: string; name: string; goal: string; color: string;
  created_at: string; task_count: number; done_count: number;
}

export interface Task {
  id: string; project_id: string; title: string; owner: string; status: Status;
  priority: Priority; due: string | null; notes: string; description: string;
  kind: Kind | null; kind_source: string; started_at: string | null; completed_at: string | null;
  position: number; created_at: string; updated_at: string;
}

export interface Finding { id: string; kind: string; severity: 'info' | 'warning' | 'critical'; text: string; }
export interface Suggestion {
  key: string; title: string; action: string; finding_ids: string[];
  impact: 'high' | 'medium' | 'low'; source: 'llm' | 'rules';
}

export const STATUSES: { id: Status; label: string; color: string }[] = [
  { id: 'planned', label: 'Planned', color: '#8E98AE' },
  { id: 'in_progress', label: 'In progress', color: '#7D96F2' },
  { id: 'blocked', label: 'Blocked', color: '#E66C63' },
  { id: 'done', label: 'Done', color: '#52B5AA' },
];

export const KIND_LABEL: Record<string, string | undefined> = {
  bug: 'Bug', feature: 'Feature', tech_debt: 'Tech debt', support: 'Support', unknown: 'Unknown',
};
