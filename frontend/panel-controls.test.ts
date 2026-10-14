// The panel's controls (Ioan, 2026-10-14: «it is a SaaS, not only a till»): a clean interface where nothing
// slides an action sheet up from the bottom and every list fills the page between the topbar and the tabbar.
// In the shell's `ios` mode an `ion-select` without `interface` opens an action sheet: every select of the
// panel is a popover (or, with 2–4 visible options, an `ion-segment`), a date picker lives in a popover,
// and every DataTable fills its page (`fill`, the page with `content-layout="detail-fill"`). A guard over the
// sources of the panel's apps, so a new screen cannot bring them back.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const SAAS_DIR = join(dirname(fileURLToPath(import.meta.url)), '..');
/** The apps whose frontend is the panel (`vite.config.ts` FRONTEND_APPS). */
const PANEL_APPS = ['hubs', 'billing', 'accounts'];

/** Every `.vue` of a panel app's frontend, but the tests' helpers. */
function vueFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return entry.name === '__tests__' ? [] : vueFiles(path);
    return entry.name.endsWith('.vue') ? [path] : [];
  });
}

const SOURCES = PANEL_APPS.flatMap((app) => vueFiles(join(SAAS_DIR, app, 'frontend'))).map((file) => ({
  file: relative(SAAS_DIR, file),
  template: templateOf(readFileSync(file, 'utf8')),
  source: readFileSync(file, 'utf8'),
}));

/** The `<template>` of a single-file component (its outermost one). */
function templateOf(source: string): string {
  const start = source.indexOf('<template>');
  const end = source.lastIndexOf('</template>');
  return start === -1 || end === -1 ? '' : source.slice(start, end);
}

/** Every opening tag `<name …>` of `template`, whole: a `>` inside a quoted attribute (`=>`) does not end it. */
function openingTags(template: string, name: string): string[] {
  const tags: string[] = [];
  const opener = new RegExp(`<${name}(?=[\\s/>])`, 'g');
  for (let match = opener.exec(template); match; match = opener.exec(template)) {
    let quote = '';
    let at = match.index + match[0].length;
    for (; at < template.length; at += 1) {
      const char = template[at];
      if (quote) {
        if (char === quote) quote = '';
      } else if (char === '"' || char === "'") {
        quote = char;
      } else if (char === '>') {
        break;
      }
    }
    tags.push(template.slice(match.index, at + 1));
  }
  return tags;
}

/** The `ion-select`s that would not open as a popover. */
const selectsWithoutPopover = (template: string) =>
  openingTags(template, 'ion-select').filter((tag) => !/\sinterface="popover"/.test(tag));

/** What slides up from the bottom: an action sheet, or a select that asks for one (or for an alert). */
const ACTION_SHEETS = /ion-action-sheet|IonActionSheet|actionSheetController|interface="(action-sheet|alert)"/;

/** A date picker painted inline in the page: it belongs in a popover (or behind an `ion-datetime-button`). */
const inlineDatetime = (template: string) =>
  openingTags(template, 'ion-datetime').length > 0 && !/<ion-popover[\s>]|<ion-datetime-button[\s>]/.test(template);

/** The DataTables that do not fill their page. */
const tablesWithoutFill = (template: string) =>
  openingTags(template, 'DataTable').filter((tag) => !/\s:?fill(?=[\s=/>])/.test(tag));

describe('the guard reads the templates as Vue does', () => {
  it('finds a select without a popover, even after an arrow function in another attribute', () => {
    expect(selectsWithoutPopover('<ion-select :value="(x) => x > 1" label="Plan"><ion-select-option /></ion-select>')).toHaveLength(1);
    expect(selectsWithoutPopover('<ion-select\n  interface="popover"\n  label="Plan"\n>')).toEqual([]);
    expect(selectsWithoutPopover('<ion-select-option value="a" />')).toEqual([]);
  });

  it('finds an action sheet, a select that asks for one and an inline date picker', () => {
    expect(ACTION_SHEETS.test('<ion-select interface="action-sheet">')).toBe(true);
    expect(ACTION_SHEETS.test("await actionSheetController.create({})")).toBe(true);
    expect(inlineDatetime('<ion-datetime presentation="date" />')).toBe(true);
    expect(inlineDatetime('<ion-popover><ion-datetime /></ion-popover>')).toBe(false);
  });

  it('finds a DataTable without `fill`', () => {
    expect(tablesWithoutFill('<DataTable :card-title="(row: Row) => row.name" testid="x">')).toHaveLength(1);
    expect(tablesWithoutFill('<DataTable\n  fill\n  testid="x"\n>')).toEqual([]);
    expect(tablesWithoutFill('<DataTable :fill="true" testid="x">')).toEqual([]);
    expect(tablesWithoutFill('<DataTable testid="x" :fillers="1">')).toHaveLength(1);
  });
});

describe('the panel: no action sheet, every list fills its page', () => {
  it('reads the panel apps’ components', () => {
    expect(SOURCES.length).toBeGreaterThan(20);
    expect(SOURCES.some((s) => s.file === join('billing', 'frontend', 'components', 'InvoicesTab.vue'))).toBe(true);
  });

  it('every ion-select opens as a popover', () => {
    const offenders = SOURCES.flatMap((s) => selectsWithoutPopover(s.template).map((tag) => `${s.file}: ${tag}`));
    expect(offenders).toEqual([]);
  });

  it('nothing opens an action sheet', () => {
    expect(SOURCES.filter((s) => ACTION_SHEETS.test(s.source)).map((s) => s.file)).toEqual([]);
  });

  it('a date picker is never painted inline', () => {
    expect(SOURCES.filter((s) => inlineDatetime(s.template)).map((s) => s.file)).toEqual([]);
  });

  it('every DataTable fills its page (rows scroll inside, toolbar and footer stay)', () => {
    const offenders = SOURCES.flatMap((s) => tablesWithoutFill(s.template).map(() => s.file));
    expect(offenders).toEqual([]);
  });
});
