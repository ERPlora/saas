// Lint of saas-next's TypeScript: the same presets as packages/ui (its config is not exported), and
// the rule that keeps TypeScript thin: the entry and the apps reach the server only through the SDK.
import pluginVue from 'eslint-plugin-vue';
import tseslint from 'typescript-eslint';

const restricted = ['fetch', 'EventSource', 'WebSocket', 'XMLHttpRequest'].map((name) => ({
  name,
  message: 'Network access goes through the SDK (@erplora/ui/sdk).',
}));

export default [
  // `static/` holds the template pages' vendored scripts (Ionic, Iconify), not our code; `packages/`
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
    // `slot="start|end|icon-only"` on ion-*/ok-* is the Web Components slot, not Vue 2 syntax.
    files: ['**/*.vue'],
    rules: { 'vue/no-deprecated-slot-attribute': ['error', { ignore: ['/^ion-/', '/^ok-/'] }] },
  },
  {
    // The entry and the apps, at the project root next to `base/` (no `apps/`, PLAN §20.2).
    files: ['frontend/**/*.{ts,vue}', '*/frontend/**/*.{ts,vue}'],
    rules: { 'no-restricted-globals': ['error', ...restricted] },
  },
];
