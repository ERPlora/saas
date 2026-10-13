// `pnpm gen:public-icons` (scripts/gen-public-icons.mjs) bakes the icons the public templates cite,
// and the sector and business type icons of hubs/data/taxonomy.json that the industries pages paint,
// into frontend/generated/public-icons.json, which `{% icon %}` (public/templatetags/icons.py)
// paints on the server (spec §8.4). The sources are the shell's own icon packages, resolved from
// @erplora/ui: `ionicons/icons` for `ion:` and `@iconify-json/{lucide,mdi,material-symbols}`.
// Nothing reaches the network, at build time or at runtime.
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import {
  buildPublicIcons,
  citedIcons,
  iconKey,
  PUBLIC_ICONS_PATH,
  renderPublicIcons,
  resolveIcon,
  taxonomyIcons,
} from '../scripts/gen-public-icons.mjs';

const SAAS_DIR = join(dirname(fileURLToPath(import.meta.url)), '..');

function templatesWith(files: Record<string, string>): string {
  const root = mkdtempSync(join(tmpdir(), 'public-icons-'));
  for (const [name, source] of Object.entries(files)) {
    const path = join(root, name);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, source);
  }
  return root;
}

describe('gen-public-icons', () => {
  it('writes frontend/generated/public-icons.json', () => {
    expect(PUBLIC_ICONS_PATH).toBe(join(SAAS_DIR, 'frontend', 'generated', 'public-icons.json'));
  });

  it('keeps the committed JSON in step with the templates and the taxonomy (run `pnpm gen:public-icons`)', () => {
    expect(readFileSync(PUBLIC_ICONS_PATH, 'utf8')).toBe(renderPublicIcons(buildPublicIcons(SAAS_DIR)));
  });

  it('reads literal {% icon %} tags and the icon arguments of {% include %} tags, nothing else', () => {
    const root = templatesWith({
      'public/a.html': '{% load icons %}{% icon "construct-outline" css_class="x" %}{% icon \'lucide:check\' %}',
      'public/components/b.html': '{% icon icon %}<p>icon="lucide:not-an-include"</p>',
      'public/c.html':
        '{% include "public/components/feature_card.html" with icon="lucide:sparkles" heading=h %}' +
        '{% include "public/partials/page_hero.html" with hero_icon="mdi:star" only %}',
      // A usage example in a comment is documentation, not a cited icon.
      'public/d.html':
        '{% comment %}Usage: {% include "public/components/x.html" with icon="lucide:example" %}' +
        '{% icon "lucide:example-too" %}{% endcomment %}{# {% icon "lucide:inline-comment" %} #}',
    });

    expect(citedIcons(root)).toEqual(['ion:construct-outline', 'lucide:check', 'lucide:sparkles', 'mdi:star']);
  });

  it('reads the icon of every sector and business type of the taxonomy, with the rows that use it', () => {
    const root = templatesWith({
      'taxonomy.json': JSON.stringify({
        _comment: 'not a row',
        sectors: [
          { code: 'hospitality', icon: 'ion:restaurant-outline', color: '#ff6b35' },
          { code: 'retail', icon: 'storefront-outline' },
        ],
        activities: [
          { code: 'bakery', icon: 'material-symbols:bakery-dining', sector: 'hospitality' },
          { code: 'restaurant', icon: 'ion:restaurant-outline', sector: 'hospitality' },
          { code: 'no_icon_yet', icon: '', sector: 'retail' },
        ],
      }),
    });

    expect(taxonomyIcons(join(root, 'taxonomy.json'))).toEqual({
      'ion:restaurant-outline': ['sector hospitality', 'business type restaurant'],
      'ion:storefront-outline': ['sector retail'],
      'material-symbols:bakery-dining': ['business type bakery'],
    });
  });

  it('bakes the taxonomy icons the templates do not cite', () => {
    const root = templatesWith({
      'public/templates/public/page.html': '{% icon "lucide:check" %}',
      'hubs/data/taxonomy.json': JSON.stringify({
        sectors: [{ code: 'hospitality', icon: 'ion:restaurant-outline' }],
        activities: [{ code: 'spa', icon: 'material-symbols:spa', sector: 'personal_services' }],
      }),
    });

    const icons = buildPublicIcons(root);

    expect(Object.keys(icons).sort()).toEqual(['ion:restaurant-outline', 'lucide:check', 'material-symbols:spa']);
    expect(icons['material-symbols:spa']).toEqual(resolveIcon('material-symbols:spa'));
  });

  it('fails naming the icon and the business type when a taxonomy icon is not in the packages', () => {
    const root = templatesWith({
      'public/templates/public/page.html': '',
      'hubs/data/taxonomy.json': JSON.stringify({
        sectors: [],
        activities: [{ code: 'bakery', icon: 'material-symbols:not-a-bakery', sector: 'hospitality' }],
      }),
    });

    expect(() => buildPublicIcons(root)).toThrow(
      /material-symbols:not-a-bakery.*business type bakery.*hubs\/data\/taxonomy\.json/s,
    );
  });

  it('defaults a bare name to Ionicons, like the template tag', () => {
    expect(iconKey('cube-outline')).toBe('ion:cube-outline');
    expect(iconKey('lucide:check')).toBe('lucide:check');
  });

  it('resolves an Ionicon to its inner SVG and viewBox', () => {
    const icon = resolveIcon('ion:construct-outline');
    expect(icon.viewBox).toBe('0 0 512 512');
    expect(icon.body.startsWith("<g stroke='currentColor'><path ")).toBe(true);
    expect(icon.body).not.toContain('<svg');
  });

  it("bakes an Ionicon self-contained: no ion-icon CSS classes, stroke and fill as attributes", () => {
    // ionicons/icons styles its outlines through ion-icon's shadow CSS (`.ionicon-fill-none`,
    // `.ionicon-stroke-width`, `.ionicon { stroke: currentColor }`). Inline, nothing defines those
    // classes: an outline icon painted as a filled blob.
    const { body } = resolveIcon('ion:information-circle-outline');
    expect(body).not.toContain('ionicon');
    expect(body.startsWith("<g stroke='currentColor'>")).toBe(true);
    expect(body).toContain("fill='none' stroke-width='32'");
    expect(resolveIcon('ion:arrow-forward-outline').body).toContain("stroke-width='48px' fill='none'");
  });

  it('resolves the Iconify sets of the shell, aliases included', () => {
    expect(resolveIcon('lucide:check')).toEqual({
      body: expect.stringContaining('stroke="currentColor"'),
      viewBox: '0 0 24 24',
    });
    expect(resolveIcon('mdi:home').viewBox).toBe('0 0 24 24');
    expect(resolveIcon('material-symbols:home').body).toContain('<path');
    // `lucide:home` is an alias of `lucide:house` in @iconify-json/lucide.
    expect(resolveIcon('lucide:home').body).toBe(resolveIcon('lucide:house').body);
  });

  it('fails with the name of an unknown icon or set, so a typo never bakes a hole', () => {
    expect(() => resolveIcon('ion:not-an-icon')).toThrow(/ion:not-an-icon/);
    expect(() => resolveIcon('lucide:not-an-icon')).toThrow(/lucide:not-an-icon/);
    expect(() => resolveIcon('fa:house')).toThrow(/fa:house.*ion, lucide, mdi, material-symbols/);
  });

  it('renders sorted, stable JSON', () => {
    const json = renderPublicIcons({
      'lucide:x': { body: '<path/>', viewBox: '0 0 24 24' },
      'ion:a': { body: '<path/>', viewBox: '0 0 512 512' },
    });
    expect(Object.keys(JSON.parse(json))).toEqual(['ion:a', 'lucide:x']);
    expect(json.endsWith('}\n')).toBe(true);
  });
});
