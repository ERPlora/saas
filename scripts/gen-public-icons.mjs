// `pnpm gen:public-icons`: bakes the icons the public pages paint into
// frontend/generated/public-icons.json, which `{% icon %}` (public/templatetags/icons.py) paints
// inline on the server (spec §8.4). Commit the result: it is versioned, and
// frontend/gen-public-icons.test.ts fails when it falls out of step with public/templates or
// hubs/data/taxonomy.json.
//
// What counts as cited (template comments aside): a literal `{% icon "set:name" %}`, and an `icon="…"` / `<x>_icon="…"`
// argument of an `{% include %}` (the component partials paint the icon their caller passes).
// Also the `icon` of every sector and business type of the taxonomy seed, which the industries
// pages (public/industries.py) paint from data no template names.
// A bare name is an Ionicon, as in the tag. The sources are the shell's own icon packages,
// resolved from @erplora/ui (packages/ui): `ionicons/icons` for `ion:`, `@iconify-json/<set>` for
// the Iconify sets. Everything is read from disk: no network, ever.
import { readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const SAAS_DIR = join(dirname(fileURLToPath(import.meta.url)), '..');

export const PUBLIC_ICONS_PATH = join(SAAS_DIR, 'frontend', 'generated', 'public-icons.json');
const TEMPLATES_DIR = join('public', 'templates');
const TAXONOMY_FILE = join('hubs', 'data', 'taxonomy.json');
const DEFAULT_SET = 'ion';
/** The Iconify sets the shell installs (packages/ui/package.json). */
const ICONIFY_SETS = ['lucide', 'mdi', 'material-symbols'];

/** `{% comment %}…{% endcomment %}` and `{# … #}`: usage examples there are documentation. */
const TEMPLATE_COMMENT = /\{%\s*comment\s*%\}[\s\S]*?\{%\s*endcomment\s*%\}|\{#[\s\S]*?#\}/g;
const ICON_TAG = /\{%\s*icon\s+["']([^"']+)["']/g;
const INCLUDE_TAG = /\{%\s*include\b[^%]*%\}/g;
const INCLUDE_ICON_ARG = /\b(?:\w+_)?icon=["']([^"']+)["']/g;

/** Resolves packages the way @erplora/ui does: they are its dependencies, not the SaaS's. */
const requireFromUi = createRequire(join(SAAS_DIR, 'packages', 'ui', 'package.json'));

/** `"cube-outline"` → `"ion:cube-outline"`; a name with a set stays as it is. */
export function iconKey(name) {
  return name.includes(':') ? name : `${DEFAULT_SET}:${name}`;
}

function htmlFiles(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return htmlFiles(path);
    return entry.name.endsWith('.html') ? [path] : [];
  });
}

/** Every icon the `.html` files under `templatesDir` cite, as sorted `set:name` keys. */
export function citedIcons(templatesDir) {
  const names = new Set();
  for (const file of htmlFiles(templatesDir)) {
    const source = readFileSync(file, 'utf8').replace(TEMPLATE_COMMENT, '');
    for (const [, name] of source.matchAll(ICON_TAG)) names.add(iconKey(name));
    for (const [include] of source.matchAll(INCLUDE_TAG)) {
      for (const [, name] of include.matchAll(INCLUDE_ICON_ARG)) names.add(iconKey(name));
    }
  }
  return [...names].sort();
}

/**
 * The icon of every sector and business type of a taxonomy file, as sorted `set:name` keys, each
 * with the rows that use it (`"sector hospitality"`, `"business type bakery"`). A blank icon is
 * skipped: the industries pages paint their default for it.
 */
export function taxonomyIcons(taxonomyFile) {
  const { sectors = [], activities = [] } = JSON.parse(readFileSync(taxonomyFile, 'utf8'));
  const uses = {};
  const rows = [
    ...sectors.map((row) => ['sector', row]),
    ...activities.map((row) => ['business type', row]),
  ];
  for (const [kind, row] of rows) {
    if (!row.icon) continue;
    (uses[iconKey(row.icon)] ??= []).push(`${kind} ${row.code}`);
  }
  return Object.fromEntries(Object.keys(uses).sort().map((key) => [key, uses[key]]));
}

let ionicons;
const iconifySets = new Map();

function camelCase(name) {
  return name.replace(/-([a-z0-9])/g, (_, char) => char.toUpperCase());
}

/** What ion-icon's shadow CSS gives the classes of `ionicons/icons`, as presentation attributes. */
const IONICON_CLASS_ATTRIBUTES = {
  'ionicon-fill-none': ['fill', 'none'],
  'ionicon-stroke-width': ['stroke-width', '32'],
};

/**
 * An Ionicon's body without ion-icon's CSS: each class becomes its attribute (replacing one the
 * element sets itself, as the CSS rule beat it) and the whole is wrapped in the stroke colour the
 * `.ionicon` root rule gave. Inline, those classes would mean nothing.
 */
function selfContainedIonicon(key, body) {
  const inlined = body.replace(/<([a-z]+)([^>]*?) class='([^']*)'([^>]*)>/g, (_, tag, before, classes, after) => {
    let attributes = `${before}${after.replace(/\/$/, '')}`;
    for (const name of classes.split(/\s+/).filter(Boolean)) {
      const attribute = IONICON_CLASS_ATTRIBUTES[name];
      if (!attribute) throw new Error(`Icon ${key}: ionicons class ${name} has no known attribute.`);
      const [prop, value] = attribute;
      const existing = new RegExp(` ${prop}='[^']*'`);
      attributes = existing.test(attributes)
        ? attributes.replace(existing, ` ${prop}='${value}'`)
        : `${attributes} ${prop}='${value}'`;
    }
    return `<${tag}${attributes}${after.endsWith('/') ? '/' : ''}>`;
  });
  return `<g stroke='currentColor'>${inlined}</g>`;
}

function resolveIonicon(key, name) {
  ionicons ??= requireFromUi('ionicons/icons');
  const url = ionicons[camelCase(name)];
  if (typeof url !== 'string') throw new Error(`Icon ${key} does not exist in ionicons.`);
  const svg = decodeURIComponent(url.slice(url.indexOf(',') + 1));
  const viewBox = /viewBox=['"]([^'"]+)['"]/.exec(svg)?.[1];
  const body = svg.slice(svg.indexOf('>') + 1, svg.lastIndexOf('</svg>'));
  if (!viewBox || !body) throw new Error(`Icon ${key}: ionicons gave an SVG this script cannot read.`);
  return { body: selfContainedIonicon(key, body), viewBox };
}

/** An Iconify icon, or the icon an alias points to (aliases may chain). */
function iconifyEntry(data, name, depth = 0) {
  if (data.icons[name]) return data.icons[name];
  const alias = data.aliases?.[name];
  if (!alias || depth > 8) return undefined;
  const parent = iconifyEntry(data, alias.parent, depth + 1);
  return parent && { ...parent, ...alias };
}

function resolveIconify(key, set, name) {
  if (!iconifySets.has(set)) iconifySets.set(set, requireFromUi(`@iconify-json/${set}/icons.json`));
  const data = iconifySets.get(set);
  const icon = iconifyEntry(data, name);
  if (!icon?.body) throw new Error(`Icon ${key} does not exist in @iconify-json/${set}.`);
  const left = icon.left ?? data.left ?? 0;
  const top = icon.top ?? data.top ?? 0;
  const width = icon.width ?? data.width ?? 16;
  const height = icon.height ?? data.height ?? 16;
  return { body: icon.body, viewBox: `${left} ${top} ${width} ${height}` };
}

/** `{ body, viewBox }` of one `set:name` key; throws with the key when it does not exist. */
export function resolveIcon(key) {
  const [set, name] = key.split(/:(.*)/s);
  if (set === DEFAULT_SET) return resolveIonicon(key, name);
  if (ICONIFY_SETS.includes(set)) return resolveIconify(key, set, name);
  throw new Error(`Icon ${key}: unknown set; the shell has ${[DEFAULT_SET, ...ICONIFY_SETS].join(', ')}.`);
}

/** The baked icons of the templates and of the taxonomy of the project at `root`. */
export function buildPublicIcons(root = SAAS_DIR) {
  const icons = Object.fromEntries(citedIcons(join(root, TEMPLATES_DIR)).map((key) => [key, resolveIcon(key)]));
  for (const [key, uses] of Object.entries(taxonomyIcons(join(root, TAXONOMY_FILE)))) {
    if (key in icons) continue;
    try {
      icons[key] = resolveIcon(key);
    } catch (error) {
      throw new Error(`${error.message} It is the icon of ${uses.join(', ')} in ${TAXONOMY_FILE}.`, { cause: error });
    }
  }
  return icons;
}

/** Stable JSON: sorted keys, two-space indent, final newline. */
export function renderPublicIcons(icons) {
  const sorted = Object.fromEntries(Object.keys(icons).sort().map((key) => [key, icons[key]]));
  return `${JSON.stringify(sorted, null, 2)}\n`;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const icons = buildPublicIcons();
  writeFileSync(PUBLIC_ICONS_PATH, renderPublicIcons(icons));
  console.log(`${PUBLIC_ICONS_PATH}: ${Object.keys(icons).length} icons`);
}
