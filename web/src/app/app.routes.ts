import { Routes } from '@angular/router';
import { authGuard, guestGuard, landingGuard } from './core/auth.guard';

// Every page is lazy-loaded.
export const routes: Routes = [
  { path: 'login', canActivate: [guestGuard], title: 'Sign in · SlipCast',
    loadComponent: () => import('./features/auth/auth.page').then((m) => m.AuthPage) },
  { path: 'signup', canActivate: [guestGuard], title: 'Create an account · SlipCast', data: { mode: 'register' },
    loadComponent: () => import('./features/auth/auth.page').then((m) => m.AuthPage) },
  { path: 'auth/callback', title: 'Signing in · SlipCast',
    loadComponent: () => import('./features/account/oauth-callback.page').then((m) => m.OAuthCallbackPage) },
  {
    path: '',
    loadComponent: () => import('./features/layout/app-layout.component').then((m) => m.AppLayoutComponent),
    children: [
      { path: '', pathMatch: 'full', canActivate: [landingGuard], title: 'SlipCast · Know when work will really ship',
        loadComponent: () => import('./features/landing/landing.page').then((m) => m.LandingPage) },
      { path: 'about', title: 'How SlipCast works',
        loadComponent: () => import('./features/about/about.page').then((m) => m.AboutPage) },
      { path: 'privacy', title: 'Privacy policy · SlipCast', data: { doc: 'privacy' },
        loadComponent: () => import('./features/legal/legal.page').then((m) => m.LegalPage) },
      { path: 'terms', title: 'Terms of use · SlipCast', data: { doc: 'terms' },
        loadComponent: () => import('./features/legal/legal.page').then((m) => m.LegalPage) },
      { path: 'invite/:token', title: 'Workspace invite · SlipCast',
        loadComponent: () => import('./features/account/invite.page').then((m) => m.InvitePage) },
      { path: 'forgot-password', canActivate: [guestGuard], title: 'Forgot password · SlipCast',
        loadComponent: () => import('./features/account/forgot-password.page').then((m) => m.ForgotPasswordPage) },
      {
        path: '',
        canActivate: [authGuard],
        children: [
          { path: 'dashboard', title: 'Dashboard · SlipCast',
            loadComponent: () => import('./features/dashboard/dashboard.page').then((m) => m.DashboardPage) },
          { path: 'imports', title: 'Imports · SlipCast',
            loadComponent: () => import('./features/imports/imports.page').then((m) => m.ImportsPage) },
          {
            path: 'settings',
            loadComponent: () => import('./features/settings/settings.layout').then((m) => m.SettingsLayout),
            children: [
              { path: '', title: 'Settings · SlipCast',
                loadComponent: () => import('./features/settings/settings.page').then((m) => m.SettingsPage) },
              { path: 'account', title: 'Account · SlipCast',
                loadComponent: () => import('./features/settings/account.view').then((m) => m.AccountSettings) },
              { path: 'team', title: 'Team · SlipCast',
                loadComponent: () => import('./features/settings/team.view').then((m) => m.TeamSettings) },
            ],
          },
          {
            path: 'projects',
            loadComponent: () => import('./features/shell/shell.component').then((m) => m.ShellComponent),
            children: [
              { path: '', title: 'Projects · SlipCast',
                loadComponent: () => import('./features/shell/welcome.page').then((m) => m.WelcomePage) },
              {
                path: ':projectId',
                title: 'Project · SlipCast',
                loadComponent: () => import('./features/project/project.page').then((m) => m.ProjectPage),
                children: [
                  { path: '', pathMatch: 'full', redirectTo: 'board' },
                  { path: 'board', loadComponent: () => import('./features/project/board.view').then((m) => m.BoardView) },
                  { path: 'delivery', loadComponent: () => import('./features/project/delivery.view').then((m) => m.DeliveryView) },
                  { path: 'forecast', loadComponent: () => import('./features/project/forecast.view').then((m) => m.ForecastView) },
                  { path: 'text', loadComponent: () => import('./features/project/text.view').then((m) => m.TextView) },
                  { path: 'advice', loadComponent: () => import('./features/project/advice.view').then((m) => m.AdviceView) },
                  { path: 'evaluation', loadComponent: () => import('./features/project/evaluation.view').then((m) => m.EvaluationView) },
                  { path: 'live', loadComponent: () => import('./features/project/live.view').then((m) => m.LiveView) },
                ],
              },
            ],
          },
        ],
      },
      { path: '**', title: 'Page not found · SlipCast',
        loadComponent: () => import('./features/not-found/not-found.page').then((m) => m.NotFoundPage) },
    ],
  },
];
