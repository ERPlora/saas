// The two CNAME records of an own domain (`CustomDomainRecords`), as the card «Own domain» shows them: in the order
// they are created, each field named and with its own «Copy», the validation one on its way until ACM gives it, and
// nothing while the domain is being removed.
import { afterEach, describe, expect, it } from 'vitest';

import { ACTIVE, PENDING } from '../__tests__/custom-domain-card';
import { ionProps, mountHubs } from '../__tests__/mount-hubs';
import en from '../locale/en.json';
import CopyField from './CopyField.vue';
import CustomDomainRecords from './CustomDomainRecords.vue';

const RECORDS = en.hubs.domain.records;

afterEach(() => {
  document.body.innerHTML = '';
});

const records = (domain: unknown) => mountHubs(CustomDomainRecords, { props: { domain } });

describe('CustomDomainRecords', () => {
  it('heads the two records and lists them in the order they are created', async () => {
    const { wrapper } = await records(PENDING);
    expect(wrapper.get('h3').text()).toBe(RECORDS.title);
    expect(wrapper.text()).toContain(RECORDS.lead);
    expect(wrapper.findAll('section').map((section) => section.attributes('data-testid'))).toEqual([
      'domain-record-validation',
      'domain-record-traffic',
    ]);
  });

  it('names each field of a record and gives it its own «Copy» and its own toasts', async () => {
    const { wrapper } = await records(PENDING);
    const validation = wrapper.get('[data-testid="domain-record-validation"]');
    expect(validation.findAll('p').map((line) => line.text())).toEqual([
      en.hubs.domain.validation.hint,
      `${RECORDS.type}: CNAME`,
      RECORDS.name,
      RECORDS.value,
    ]);
    const copied = { copiedText: RECORDS.copied, failedText: RECORDS.copyFailed };
    expect(validation.findAllComponents(CopyField).map((field: { props: () => unknown }) => field.props())).toEqual([
      { value: PENDING.validation.name, label: RECORDS.name, copyLabel: RECORDS.copyName, ...copied },
      { value: PENDING.validation.value, label: RECORDS.value, copyLabel: RECORDS.copyValue, ...copied },
    ]);
  });

  it('a validation record ACM has not given yet is on its way, with a small outlined «Look again» that asks for it', async () => {
    const { wrapper } = await records({ ...PENDING, validation: null });
    expect(wrapper.get('[data-testid="domain-validation-coming"]').text()).toContain(en.hubs.domain.validation.coming);
    const again = wrapper.get('[data-testid="domain-look-again"]');
    expect(again.text()).toBe(en.hubs.domain.validation.lookAgain);
    expect(ionProps(again, 'fill', 'size')).toEqual({ fill: 'outline', size: 'small' });
    await again.trigger('click');
    expect(wrapper.emitted('lookAgain')).toEqual([[]]);
  });

  it('shows nothing of a domain that is being removed', async () => {
    const { wrapper } = await records({ ...ACTIVE, state: 'removing' });
    expect(wrapper.find('h3').exists()).toBe(false);
    expect(wrapper.findAll('section')).toHaveLength(0);
  });
});
