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
          { path: 'delivery', loadComponent: () => import('./features/project/delivery.view').then((m) => m.DeliveryView) },
          { path: 'forecast', loadComponent: () => import('./features/project/forecast.view').then((m) => m.ForecastView) },
          { path: 'text', loadComponent: () => import('./features/project/text.view').then((m) => m.TextView) },
          { path: 'advice', loadComponent: () => import('./features/project/advice.view').then((m) => m.AdviceView) },
          { path: 'evaluation', loadComponent: () => import('./features/project/evaluation.view').then((m) => m.EvaluationView) },
        ],
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
