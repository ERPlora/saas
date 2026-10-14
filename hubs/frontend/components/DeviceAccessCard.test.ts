// «On your devices» (mockups `business.html` Summary; it replaces the old QR page): the business's
// address to open on the till, the tablet or the phone, with «Copy», and — on the web only — the
// apps for Windows and Android (the public download doors, `/app/download/<platform>/`).
import { applySurface } from '@erplora/ui/shell';
import { afterEach, describe, expect, it } from 'vitest';

import { ionProps, mountHubs } from '../__tests__/mount-hubs';
import CopyField from './CopyField.vue';
import DeviceAccessCard from './DeviceAccessCard.vue';

afterEach(() => {
  applySurface('web');
  document.body.innerHTML = '';
});

describe('DeviceAccessCard', () => {
  it('on the web: the address to copy and the two apps', async () => {
    const { wrapper } = await mountHubs(DeviceAccessCard, { props: { host: 'bakery.erplora.com' } });
    expect(wrapper.get('.page-eyebrow').text()).toBe('On your devices');
    expect(wrapper.get('h2').text()).toBe('Enter from anywhere');
    expect(wrapper.text()).toContain('Open this address in the browser of the till, the tablet or the phone, or use the app.');
    expect(wrapper.findComponent(CopyField).props('value')).toBe('bakery.erplora.com');
    expect(ionProps(wrapper.get('[data-testid="device-windows"]'), 'href')).toEqual({ href: '/app/download/windows/' });
    expect(ionProps(wrapper.get('[data-testid="device-android"]'), 'href')).toEqual({ href: '/app/download/android/' });
  });

  it('inside the app: only the address, for the other devices', async () => {
    applySurface('mobile');
    const { wrapper } = await mountHubs(DeviceAccessCard, { props: { host: 'bakery.erplora.com' }, locale: 'es' });
    expect(wrapper.text()).toContain('Abre esta dirección en el navegador de tus otros dispositivos.');
    expect(wrapper.find('[data-testid="device-windows"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="device-android"]').exists()).toBe(false);
  });
});
