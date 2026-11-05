import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from './auth.service';

// inject() must run before the first await, while Angular's injection context is active.
export const authGuard: CanActivateFn = async () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  return (await auth.ensureLoaded()) || router.parseUrl('/login');
};

/** Sign-in page: signed-in users go straight to their dashboard. */
export const guestGuard: CanActivateFn = async () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  return (await auth.ensureLoaded()) ? router.parseUrl('/dashboard') : true;
};

/** Public landing page at "/": signed-in users see their dashboard instead. */
export const landingGuard: CanActivateFn = guestGuard;
