// PUBLIC-F11 on the public web of erplora.com: a button that leads to another page is a real link, so it leads on even
// pressed before the page's script has run, and it looks and reacts exactly like an ion-button, at rest and under the
// pointer.
// flow: PUBLIC-F11
import { execFileSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Route } from '@playwright/test';

import { djangoEnv } from './django-env';
import { expect, test } from './public-test';

const HERE = dirname(fileURLToPath(import.meta.url));
const SAAS_DIR = join(HERE, '..', '..');

test.beforeAll(() => {
  // The industries are the taxonomy every deploy seeds (saas-migrate runs seed_taxonomy): the same here.
  execFileSync('uv', ['run', 'python', 'manage.py', 'seed_taxonomy'], { cwd: SAAS_DIR, env: djangoEnv(true) });
});

// Reduced motion paints every revealed block at once, so a full-page capture shows the whole page (as public-dark.spec.ts).
test.use({ locale: 'en-GB', reducedMotion: 'reduce' });

test('PUBLIC-F11 on a slow device, the buttons of the public web lead on even pressed before the page script has run', async ({
  page,
}) => {
  // The page's scripts have not arrived when the person presses (saas#238): held until the end. The stylesheet has,
  // so the page already reads whole and its buttons show.
  const held: Route[] = [];
  await page.route('**/static/spa/**/*.js', (route) => {
    held.push(route);
  });

  // By their address alone: what is under test is that pressing it leads there, whatever the element is.
  const buttons: Array<[string, string, RegExp]> = [
    ['/', 'nav.ep-navbar [href="/launch"]', /\/launch$/],
    ['/', 'nav.ep-navbar [href="/demo/"]', /\/demo\/$/],
    ['/', 'section.hero-bg [href="/launch"]', /\/launch$/],
    ['/', 'section.hero-bg [href="/demo/"]', /\/demo\/$/],
    ['/', 'section.hero-bg [href="/download/"]', /\/download\/$/],
    ['/', '#planes [href="/launch"] >> nth=1', /\/launch$/],
    ['/', '.ep-cta-band [href="/demo/"]', /\/demo\/$/],
    ['/pricing/', '.ep-pricing-card [href="/launch"] >> nth=0', /\/launch$/],
    ['/pricing/', '#more-capacity [href="/launch"]', /\/launch$/],
    ['/pricing/starter/', 'main [href="/launch"] >> nth=0', /\/launch$/],
    ['/pricing/no-such-plan/', 'main [href="/"]', /\/$/],
    ['/industries/', 'main [href="/apps/"]', /\/apps\/$/],
    ['/industries/hair_salon/', 'main [href="/launch"] >> nth=0', /\/launch$/],
    ['/features/', '.ep-cta-band [href="/launch"] >> nth=0', /\/launch$/],
    ['/updates/', '.ep-cta-band [href="/legal/terms/"]', /\/legal\/terms\/$/],
    ['/collaborate/', 'main [href="/contact/?subject=collaborate"] >> nth=0', /\/contact\/\?subject=collaborate$/],
    ['/download/', 'main [href="/launch"]', /\/launch$/],
    ['/app/', 'main [href="/pricing/"]', /\/pricing\/$/],
  ];
  for (const [path, button, destination] of buttons) {
    await page.goto(path, { waitUntil: 'commit' });
    await expect(page.locator(button), `${path} ${button}`).toBeVisible();
    // The control: the page's script has really not run, so nothing but the HTML can lead anywhere.
    expect(await page.evaluate(() => customElements.get('ion-button') === undefined), `${path} ${button}`).toBe(true);

    await page.locator(button).click();
    await expect(page, `${path} ${button}`).toHaveURL(destination);
  }

  // Before the script it already looks like a button, and not like a text link: the stylesheet is enough.
  await page.goto('/', { waitUntil: 'commit' });
  await expect(page.locator('section.hero-bg a.ep-button--large >> nth=0')).toHaveCSS('border-top-left-radius', '10px');
  expect(await page.evaluate(() => customElements.get('ion-button') === undefined)).toBe(true);

  await page.unrouteAll({ behavior: 'ignoreErrors' });
  await Promise.all(held.map((route) => route.continue().catch(() => undefined)));
});

test('PUBLIC-F11 a button that is a real link looks and reacts exactly like an ion-button', async ({ page }) => {
  /** One of each the public web uses: the attributes of the ion-button and the classes of the link it became. */
  const looks = (where: string, variants: Array<[Record<string, string>, string[]]>) => ({ where, variants });
  const scenes = [
    looks('main', [
      [{}, []],
      [{ size: 'small' }, ['ep-button--small']],
      [{ size: 'large' }, ['ep-button--large']],
      [{ fill: 'outline' }, ['ep-button--outline']],
      [{ fill: 'outline', size: 'small' }, ['ep-button--outline', 'ep-button--small']],
      [{ fill: 'outline', size: 'large' }, ['ep-button--outline', 'ep-button--large']],
      [{ fill: 'clear', size: 'small' }, ['ep-button--clear', 'ep-button--small']],
      [{ fill: 'clear', size: 'large' }, ['ep-button--clear', 'ep-button--large']],
      [{ size: 'large', color: 'light' }, ['ep-button--large', 'ep-button--light']],
      [{ expand: 'block' }, ['ep-button--block']],
      [{ expand: 'block', fill: 'outline' }, ['ep-button--block', 'ep-button--outline']],
      [{ expand: 'block', size: 'large' }, ['ep-button--block', 'ep-button--large']],
    ]),
    looks('.ep-cta-band--solid .ep-cta-band__actions', [
      [{ size: 'large', color: 'light' }, ['ep-button--large', 'ep-button--light']],
    ]),
  ];

  /** What a person sees of it, read off the element that paints it: an ion-button's inner link, or the link itself. */
  const seen = (id: string) =>
    page.evaluate((id) => {
      const outer = document.getElementById(id) as HTMLElement;
      const painted = outer.shadowRoot?.querySelector<HTMLElement>('.button-native') ?? outer;
      const box = outer.getBoundingClientRect();
      const host = getComputedStyle(outer);
      const style = getComputedStyle(painted);
      const overlay = getComputedStyle(painted, '::after');
      return {
        width: Math.round(box.width * 2) / 2,
        height: Math.round(box.height * 2) / 2,
        margin: host.margin,
        opacity: host.opacity,
        fontKerning: host.fontKerning,
        background: style.backgroundColor,
        color: style.color,
        border: [style.borderTopWidth, style.borderTopStyle, style.borderTopColor],
        radius: style.borderTopLeftRadius,
        padding: style.padding,
        font: [style.fontSize, style.fontWeight, style.letterSpacing, style.lineHeight, style.textTransform],
        align: style.textAlign,
        underline: style.textDecorationLine,
        cursor: style.cursor,
        overlay: [overlay.backgroundColor, overlay.opacity],
      };
    }, id);

  await page.goto('/');
  await page.waitForLoadState('domcontentloaded');
  await page.waitForFunction(() => customElements.get('ion-button') !== undefined);
  // On the solid band an outline button turns white: no ion-button is left there to compare it with.
  await expect(page.locator('.ep-cta-band--solid a.ep-button--outline').first()).toHaveCSS('color', 'rgb(255, 255, 255)');
  for (const [scene, { where, variants }] of scenes.entries()) {
    await page.evaluate(
      ({ scene, where, variants }) => {
        const row = document.createElement('div');
        row.style.width = '24rem';
        const icon = (attribute: string, value: string) => {
          const span = document.createElement('span');
          span.setAttribute(attribute, value);
          span.textContent = '>';
          return span;
        };
        variants.forEach(([attributes, classes], index) => {
          const button = document.createElement('ion-button');
          button.id = `parity-${scene}-${index}-button`;
          Object.entries(attributes).forEach(([name, value]) => button.setAttribute(name, value));
          button.setAttribute('href', '#');
          button.style.setProperty('--transition', 'none');
          button.append('Start free', icon('slot', 'end'));
          const link = document.createElement('a');
          link.id = `parity-${scene}-${index}-link`;
          link.className = ['ep-button', ...classes].join(' ');
          link.href = '#';
          link.style.transition = 'none';
          link.append('Start free', icon('class', 'ep-button__end'));
          row.append(button, link);
        });
        document.querySelector(where)?.append(row);
      },
      { scene, where, variants },
    );
    for (const index of variants.keys()) {
      const name = `${where} ${JSON.stringify(variants[index][0])}`;
      const button = `parity-${scene}-${index}-button`;
      const link = `parity-${scene}-${index}-link`;
      await expect(page.locator(`#${button} .button-native`), name).toBeVisible();
      expect(await seen(link), `${name} at rest`).toEqual(await seen(button));

      await page.locator(`#${button}`).hover();
      const hovered = await seen(button);
      await page.locator(`#${link}`).hover();
      expect(await seen(link), `${name} under the pointer`).toEqual(hovered);
    }
  }
});
