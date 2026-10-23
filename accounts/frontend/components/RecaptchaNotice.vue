<script setup lang="ts">
// Google's notice of reCAPTCHA Enterprise, under every sign-in form whose POST carries its token
// (accounts/frontend/recaptcha.ts): the badge Google paints is hidden (the style frontend/recaptcha.ts puts in with
// Google's script), which its terms allow only with this text where the person is (reCAPTCHA FAQ). Showing it also
// loads Google's script, so it watches the page before the submit and the token comes at once. Nothing without a
// site key (reCAPTCHA off, the default since 2026-10-23).
import { onMounted } from 'vue';

import { loadRecaptcha } from '../../../frontend/recaptcha';
import { recaptchaSiteKey } from '../recaptcha';

const PRIVACY = 'https://policies.google.com/privacy';
const TERMS = 'https://policies.google.com/terms';

/** The page's site key by default (`spa-config.recaptchaSiteKey`). */
const props = defineProps<{ siteKey?: string }>();
const key = props.siteKey ?? recaptchaSiteKey();

onMounted(() => {
  if (!key) return;
  loadRecaptcha(key).catch((error: unknown) => {
    console.error('reCAPTCHA: the script did not load', error);
  });
});
</script>

<template>
  <p
    v-if="key"
    class="recaptcha-notice"
    data-testid="recaptcha-notice"
  >
    <i18n-t
      keypath="accounts.recaptcha.notice"
      tag="span"
    >
      <template #privacy>
        <a
          :href="PRIVACY"
          target="_blank"
          rel="noopener"
        >{{ $t('accounts.recaptcha.privacy') }}</a>
      </template>
      <template #terms>
        <a
          :href="TERMS"
          target="_blank"
          rel="noopener"
        >{{ $t('accounts.recaptcha.terms') }}</a>
      </template>
    </i18n-t>
  </p>
</template>

<style scoped>
.recaptcha-notice {
  margin: 12px 0 0;
  font-size: 12px;
  line-height: 1.4;
  color: var(--ion-color-medium);
  text-align: center;
}

.recaptcha-notice a {
  color: inherit;
  text-decoration: underline;
}
</style>
