<script setup lang="ts">
// The two CNAME records the owner creates at their domain provider, in that order, each field with «Copy»: the
// validation one first, which stays for good, and the one that points to ERPlora once the certificate is ready.
// Nothing while the domain is being removed.
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';

import type { CustomDomainOut, DnsRecordOut } from '../../../frontend/sdk-types/hubs-custom-domains';
import CopyField from './CopyField.vue';

const props = defineProps<{ domain: CustomDomainOut }>();
const emit = defineEmits<{ lookAgain: [] }>();

/** The two records, in the order they are created; the validation one is `null` until ACM has it. */
const records = computed<Array<{ key: 'validation' | 'traffic'; record: DnsRecordOut | null }>>(() => {
  const now = props.domain;
  if (now.state === 'removing') return [];
  return [
    { key: 'validation', record: now.validation },
    { key: 'traffic', record: now.traffic },
  ];
});
</script>

<template>
  <div
    v-if="records.length"
    class="ion-margin-top"
  >
    <h3>
      <strong>{{ $t('hubs.domain.records.title') }}</strong>
    </h3>
    <p>{{ $t('hubs.domain.records.lead') }}</p>
    <section
      v-for="item in records"
      :key="item.key"
      class="ion-margin-top"
      :data-testid="`domain-record-${item.key}`"
    >
      <h4>
        <strong>{{ $t(`hubs.domain.${item.key}.title`) }}</strong>
      </h4>
      <p>{{ $t(`hubs.domain.${item.key}.hint`) }}</p>
      <template v-if="item.record">
        <p>
          {{ $t('hubs.domain.records.type') }}:
          <strong data-testid="domain-record-type">{{ item.record.type }}</strong>
        </p>
        <p>{{ $t('hubs.domain.records.name') }}</p>
        <CopyField
          :value="item.record.name"
          :label="$t('hubs.domain.records.name')"
          :copy-label="$t('hubs.domain.records.copyName')"
          :copied-text="$t('hubs.domain.records.copied')"
          :failed-text="$t('hubs.domain.records.copyFailed')"
        />
        <p>{{ $t('hubs.domain.records.value') }}</p>
        <CopyField
          :value="item.record.value"
          :label="$t('hubs.domain.records.value')"
          :copy-label="$t('hubs.domain.records.copyValue')"
          :copied-text="$t('hubs.domain.records.copied')"
          :failed-text="$t('hubs.domain.records.copyFailed')"
        />
      </template>
      <div
        v-else
        data-testid="domain-validation-coming"
      >
        <p>{{ $t('hubs.domain.validation.coming') }}</p>
        <ion-button
          data-testid="domain-look-again"
          fill="outline"
          size="small"
          @click="emit('lookAgain')"
        >
          {{ $t('hubs.domain.validation.lookAgain') }}
        </ion-button>
      </div>
    </section>
  </div>
</template>
