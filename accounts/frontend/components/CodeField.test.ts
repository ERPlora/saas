// The code input of every second-factor screen (sign-in, setup, reauthentication), ported from the
// ERPlora/saas partial `account/_auth_code_field.html`: one outlined md input, numeric keypad and the
// browser's one-time-code autofill, room for a recovery code (16), its error under it.
import { IonInput } from '@ionic/vue';
import { describe, expect, it, vi } from 'vitest';

import { mountAccountPage } from '../__tests__/mount-account-page';
import CodeField from './CodeField.vue';

type Control = HTMLElement & { errorText?: string };

function mountField(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  return mountAccountPage(CodeField, { locale, props: { modelValue: '', ...props } });
}

describe('CodeField', () => {
  it('is the outlined md input of the template, made for a 6-digit code or a recovery code', async () => {
    const { wrapper } = await mountField();
    const input = wrapper.getComponent(IonInput);
    // `mode` is not a prop of Ionic Vue's proxies: it reaches the element as an attribute.
    expect([input.attributes('mode'), input.props('type'), input.props('fill'), input.props('labelPlacement')]).toEqual([
      'md',
      'text',
      'outline',
      'floating',
    ]);
    expect([input.props('label'), input.props('placeholder')]).toEqual(['Verification code', '000000']);
    expect([input.props('inputmode'), input.props('autocomplete'), input.props('maxlength'), input.props('required')]).toEqual([
      'numeric',
      'one-time-code',
      16,
      true,
    ]);
    expect(input.classes()).toContain('otp-input');
  });

  it('hands what is typed to its v-model', async () => {
    const update = vi.fn();
    const { wrapper } = await mountField({ 'onUpdate:modelValue': update });
    await wrapper.getComponent(IonInput).setValue('123456');
    expect(update).toHaveBeenCalledWith('123456');
  });

  it('paints its error under the input and marks it invalid', async () => {
    const { wrapper } = await mountField({ error: 'Incorrect code.' });
    const input = wrapper.getComponent(IonInput);
    expect((input.element as Control).errorText).toBe('Incorrect code.');
    expect(input.classes()).toEqual(expect.arrayContaining(['ion-invalid', 'ion-touched']));
  });

  it('is not invalid without an error', async () => {
    const { wrapper } = await mountField();
    expect(wrapper.getComponent(IonInput).classes()).not.toContain('ion-invalid');
  });

  it('speaks Spanish', async () => {
    const { wrapper } = await mountField({}, 'es');
    expect(wrapper.getComponent(IonInput).props('label')).toBe('Código de verificación');
  });
});
