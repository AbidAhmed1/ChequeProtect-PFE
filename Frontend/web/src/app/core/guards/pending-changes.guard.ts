import { CanDeactivateFn } from '@angular/router';
import { Observable } from 'rxjs';

export interface ComponentCanDeactivate {
  canDeactivate: () => boolean | Observable<boolean>;
}

/**
 * PendingChangesGuard: Warns user about unsaved changes before leaving a route.
 */
export const pendingChangesGuard: CanDeactivateFn<ComponentCanDeactivate> = (component) => {
  return component.canDeactivate ? component.canDeactivate() : true;
};
