import { effect, inject, signal, untracked } from '@angular/core';
import { Api, errorMessage } from '../../core/api.service';
import { ProjectContext } from './project.context';

/** Fetches project data and refetches whenever the project or its tickets change. */
export function projectResource<T>(path: (id: string) => string, params: () => Record<string, string> = () => ({})) {
  const api = inject(Api);
  const ctx = inject(ProjectContext);
  const data = signal<T | null>(null);
  const error = signal('');
  const loading = signal(false);
  effect(() => {
    const id = ctx.id();
    ctx.version();
    const p = params();
    if (!id) return;
    untracked(() => {
      loading.set(true);
      api.get<T>(path(id), p)
        .then((d) => { data.set(d); error.set(''); })
        .catch((e) => error.set(errorMessage(e)))
        .finally(() => loading.set(false));
    });
  });
  return { data, error, loading };
}
