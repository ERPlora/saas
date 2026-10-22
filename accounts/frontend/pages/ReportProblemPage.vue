<script setup lang="ts">
// «Report a problem» (`/report-a-problem`, the user menu; ACCOUNTS-F38, PLAN-SAAS §1.1): «Subject» and «What
// happened?» go to the support mailbox (`accounts.support.report`) with the account, its businesses, the page the
// person came from and the browser, which the screen says; «Report sent» names the address support answers to. A
// refusal keeps what was typed: a field's (422) under it, the rest (the limit, a mail that could not leave, no
// network) above «Send report», which can be pressed again. Nothing is sold here: it shows on every surface.
import { InlineFeedback } from '@erplora/ui/components';
import { AppPage, HubIcon } from '@erplora/ui/shell';
import { useCommand } from '@erplora/ui/sdk';
import { IonButton, IonCard, IonCardContent, IonInput, IonSpinner, IonTextarea } from '@ionic/vue';
import { computed, shallowRef } from 'vue';
import { useRouter } from 'vue-router';

import { useErrorText } from '../error-text';

/** Where Back goes when the page was opened on its own (a link, a reload). */
const PANEL_HOME = '/businesses';

const router = useRouter();
const { text } = useErrorText();
const report = useCommand('accounts.support.report');

const subject = shallowRef('');
const description = shallowRef('');
/** The address support answers to, once the report left. */
const replyTo = shallowRef<string | null>(null);
/** The panel's page the person came from, as the router remembers it (`null` when opened on its own). */
function cameFrom(): string | null {
  return (router.options.history.state.back as string | null | undefined) ?? null;
}

const ready = computed(() => !!subject.value.trim() && !!description.value.trim() && !report.pending.value);
const fieldErrors = computed<Readonly<Record<string, string>>>(() =>
  report.error.value?.status === 422 ? (report.error.value.fields ?? {}) : {},
);
/** What a refusal that is not about one field says (the limit, the mail, the network). */
const failure = computed(() => (report.error.value && report.error.value.status !== 422 ? text(report.error.value) : ''));

async function send(): Promise<void> {
  if (!ready.value) return;
  try {
    const sent = await report.run({ subject: subject.value.trim(), description: description.value.trim(), page: cameFrom() });
    replyTo.value = sent.reply_to;
  } catch {
    // Said on screen from `report.error`; what was typed stays.
  }
}

function back(): void {
  if (cameFrom()) router.back();
  else void router.push(PANEL_HOME);
}
</script>

<template>
  <AppPage
    :title="$t('accounts.report.title')"
    content-layout="detail"
    :back-href="PANEL_HOME"
  >
    <ion-card
      v-if="replyTo"
      data-testid="report-sent"
    >
      <ion-card-content class="ion-padding">
        <h2 class="card-title sent-title">
          <HubIcon
            name="ion:checkmark-circle-outline"
            class="sent-icon"
            aria-hidden="true"
          />
          {{ $t('accounts.report.sentTitle') }}
        </h2>
        <p class="card-text">
          {{ $t('accounts.report.sentBody', { email: replyTo }) }}
        </p>
        <div class="card-actions">
          <ion-button
            data-testid="report-back"
            @click="back"
          >
            {{ $t('accounts.report.back') }}
          </ion-button>
        </div>
      </ion-card-content>
    </ion-card>

    <ion-card
      v-else
      data-testid="report-card"
    >
      <ion-card-content class="ion-padding">
        <p
          class="card-text intro"
          data-testid="report-intro"
        >
          {{ $t('accounts.report.intro') }}
        </p>
        <form
          class="report-form"
          novalidate
          @submit.prevent="send"
        >
          <ion-input
            v-model="subject"
            data-testid="report-subject"
            mode="md"
            fill="outline"
            label-placement="floating"
            :maxlength="150"
            :label="$t('accounts.report.subject')"
            :error-text="fieldErrors.subject"
            :class="{ 'ion-invalid': !!fieldErrors.subject, 'ion-touched': !!fieldErrors.subject }"
          />
          <ion-textarea
            v-model="description"
            data-testid="report-description"
            mode="md"
            fill="outline"
            label-placement="floating"
            :auto-grow="true"
            :rows="6"
            :maxlength="5000"
            :label="$t('accounts.report.description')"
            :placeholder="$t('accounts.report.descriptionPlaceholder')"
            :error-text="fieldErrors.description"
            :class="{ 'ion-invalid': !!fieldErrors.description, 'ion-touched': !!fieldErrors.description }"
          />
          <p
            class="hint"
            data-testid="report-context"
          >
            {{ $t('accounts.report.context') }}
          </p>
          <InlineFeedback
            v-if="failure"
            data-testid="report-error"
            tone="danger"
          >
            {{ failure }}
          </InlineFeedback>
          <div class="card-actions">
            <ion-button
              data-testid="report-send"
              type="submit"
              :disabled="!ready"
            >
              <ion-spinner
                v-if="report.pending.value"
                slot="start"
                name="crescent"
              />
              {{ $t('accounts.report.send') }}
            </ion-button>
          </div>
        </form>
      </ion-card-content>
    </ion-card>
  </AppPage>
</template>

<style scoped src="../components/account-card.css"></style>
<style scoped>
.intro {
  margin: 0 0 16px;
}
.report-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.report-form .hint,
.report-form .card-actions {
  margin: 0;
}
.sent-title {
  display: flex;
  align-items: center;
  gap: 8px;
}
.sent-icon {
  font-size: 1.4rem;
  color: var(--ion-color-success);
}
</style>
