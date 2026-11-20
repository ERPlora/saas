import type { DataTableAction } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';

import en from './locale/en.json';
import es from './locale/es.json';
import { withRowNames } from './row-names';

type Row = { id: string; name: string };
const t = (key: string, values: Record<string, unknown>) => `${key}|${String(values.action)}|${String(values.name)}`;
const ROW: Row = { id: '7', name: 'Bar La Plaza' };

describe('withRowNames', () => {
  it('names each action with its row for a screen reader, its own label first', () => {
    const actions: DataTableAction<Row>[] = [
      { id: 'edit', label: 'Edit', icon: 'ion:create-outline' },
      { id: 'archive', label: (row) => `Archive #${row.id}`, menuOnly: true },
    ];
    const [edit, archive] = withRowNames(t, (row: Row) => row.name, actions);
    expect(edit.ariaLabel?.(ROW)).toBe('saas.rowAction|Edit|Bar La Plaza');
    expect(archive.ariaLabel?.(ROW)).toBe('saas.rowAction|Archive #7|Bar La Plaza');
  });

  it('keeps everything else of each action as it was', () => {
    const disabled = () => true;
    const [edit] = withRowNames(t, (row: Row) => row.name, [
      { id: 'edit', label: 'Edit', icon: 'ion:create-outline', color: 'danger', pinned: true, disabled },
    ]);
    expect(edit).toMatchObject({ id: 'edit', label: 'Edit', icon: 'ion:create-outline', color: 'danger', pinned: true, disabled });
  });

  it('says it in English and in Spanish, the action first and then the row', () => {
    expect([en.saas.rowAction, es.saas.rowAction]).toEqual(['{action}: {name}', '{action}: {name}']);
  });
});
