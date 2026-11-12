// Lint of the SaaS's TypeScript: the same presets as packages/ui (its config is not exported), the
// rule that keeps TypeScript thin (the entry and the apps reach the server only through the SDK), and
// the one that keeps an e2e from stopping Playwright's Node to read every mail of its stack.
import pluginVue from 'eslint-plugin-vue';
import tseslint from 'typescript-eslint';

const restricted = ['fetch', 'EventSource', 'WebSocket', 'XMLHttpRequest'].map((name) => ({
  name,
  message: 'Network access goes through the SDK (@erplora/ui/sdk).',
}));

// `readMails` reads and parses every file of the mail folder with Node stopped, and a stack's folder keeps every
// mail of every run (hundreds of ms each time, seconds on a busy machine: saas#363).
const wholeMailFolder = ['@erplora/ui/testing/mail', '@erplora/ui/testing'].map((name) => ({
  name,
  importNames: ['readMails'],
  message: 'It stops the e2e reading the whole mail folder: read the mails written from the action on with readMailsSince.',
}));

export default [
  // `static/` holds the template pages' vendored scripts (Ionic), not our code; `packages/`
  // the live and ui submodules, linted in their repos; `.venv/` the scripts Django and ninja ship.
  {
    ignores: [
      'frontend/dist/**',
      'staticfiles/**',
      'static/**',
      'node_modules/**',
      'coverage/**',
      'packages/**',
      '.venv/**',
    ],
  },
  ...tseslint.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
    files: ['**/*.vue'],
    languageOptions: { parserOptions: { parser: tseslint.parser } },
  },
  {
    // `slot="start|end|icon-only"` on ion-* (and on HubIcon, whose root is an ion-icon) is the Web
    // Components slot, not Vue 2 syntax.
    files: ['**/*.vue'],
    rules: { 'vue/no-deprecated-slot-attribute': ['error', { ignore: ['/^ion-/', 'HubIcon'] }] },
  },
  {
    // The entry and the apps, at the project root next to `base/` (there is no `apps/` folder).
    files: ['frontend/**/*.{ts,vue}', '*/frontend/**/*.{ts,vue}'],
    rules: { 'no-restricted-globals': ['error', ...restricted] },
  },
  {
    files: ['tests/e2e/**/*.ts'],
    rules: { 'no-restricted-imports': ['error', { paths: wholeMailFolder }] },
  },
];
