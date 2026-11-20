import type { DataTableAction } from '@erplora/ui/components';

type Translate = (key: string, values: Record<string, unknown>) => string;

/** Gives each row action of a list the name a screen reader says, with whom it affects: «Change role: Carlos Ruiz».
 *  Its short label goes first, as it is what voice control hears (WCAG 2.5.3); the text on screen does not change. */
export function withRowNames<T>(t: Translate, nameOf: (row: T) => string, actions: DataTableAction<T>[]): DataTableAction<T>[] {
  return actions.map((action) => ({
    ...action,
    ariaLabel: (row: T) =>
      t('saas.rowAction', { action: typeof action.label === 'function' ? action.label(row) : action.label, name: nameOf(row) }),
  }));
}
