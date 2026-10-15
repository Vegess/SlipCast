import { Routes } from '@angular/router';
import { authGuard, guestGuard } from './core/auth.guard';

export const routes: Routes = [
  { path: 'login', canActivate: [guestGuard],
    loadComponent: () => import('./features/auth/auth.page').then((m) => m.AuthPage) },
  {
    path: '',
    canActivate: [authGuard],
    loadComponent: () => import('./features/shell/shell.component').then((m) => m.ShellComponent),
    children: [
      { path: '', loadComponent: () => import('./features/shell/welcome.page').then((m) => m.WelcomePage) },
      {
        path: 'projects/:projectId',
        loadComponent: () => import('./features/project/project.page').then((m) => m.ProjectPage),
        children: [
          { path: '', pathMatch: 'full', redirectTo: 'board' },
          { path: 'board', loadComponent: () => import('./features/project/board.view').then((m) => m.BoardView) },
        ],
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
