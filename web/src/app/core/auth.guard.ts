import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService, safeNext } from './auth.service';

// inject() must run before the first await, while Angular's injection context is active.

/** Signed-out visitors go to sign-in, which brings them back here afterwards. */
export const authGuard: CanActivateFn = async (_route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (await auth.ensureLoaded()) return true;
  return router.createUrlTree(['/login'], { queryParams: state.url === '/dashboard' ? {} : { next: state.url } });
};

/** Sign-in pages: signed-in users go where they were heading, or to their dashboard. */
export const guestGuard: CanActivateFn = async (route) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (!(await auth.ensureLoaded())) return true;
  return router.parseUrl(safeNext(route.queryParamMap.get('next')) ?? '/dashboard');
};

/** Public landing page at "/": signed-in users see their dashboard instead. */
export const landingGuard: CanActivateFn = guestGuard;
