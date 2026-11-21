import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-settings-layout',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  template: `
  <div class="mx-auto max-w-3xl px-4 py-8 sm:px-8">
    <h1 class="anim-fade text-3xl font-bold">Settings</h1>
    <p class="note mt-1">Your profile, how you sign in, and who's in your workspace.</p>
    <nav class="mb-8 mt-6 flex gap-1 border-b border-line" aria-label="Settings sections">
      @for (t of tabs; track t[0]) {
        <a [routerLink]="t[0]" routerLinkActive="tab-active !text-fg" [routerLinkActiveOptions]="{ exact: true }" ariaCurrentWhenActive="page"
           class="tab-link -mb-px border-b-2 border-transparent px-3 pb-2.5 text-sm font-medium text-muted transition-colors hover:text-fg">{{ t[1] }}</a>
      }
    </nav>
    <router-outlet />
  </div>`,
})
export class SettingsLayout {
  readonly tabs = [['/settings', 'General'], ['/settings/account', 'Account'], ['/settings/team', 'Team']] as const;
}
