// The sign-up of a business (round 17 §2.3; mockups `launch.html` «first», `businesses.html` «create»):
// name, country and an optional business type, the address the name proposes as it is typed
// (`hubs.address.propose`), and `hubs.business.create`. Shared by the launcher, the empty Businesses
// and the «Create business» dialog: in the dialog the dialog's own button submits (`submit()`).
import { afterEach, describe, expect, it, vi } from 'vitest';
import { h, ref } from 'vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));

import { toastSuccess } from '@erplora/ui/shell';

import { apiError, type ApiCall, describeCall, flush, ionProps, mountHubs, optionValue } from '../__tests__/mount-hubs';
import BusinessCreateForm from './BusinessCreateForm.vue';

const TYPES = {
  business_types: [
    { code: 'bakery', name: 'Bakery and pastry', description: '', icon: '', color: '', sector: null, vertical: 'bakery', updated_at: '' },
    { code: 'salon', name: 'Hair salon', description: '', icon: '', color: '', sector: null, vertical: '', updated_at: '' },
  ],
};

const DETAIL = { id: 'h1', name: 'Pastelería Dulce', host: 'pasteleria-dulce.localhost:8000', status: 'preparing' };

type Handler = (call: ReturnType<typeof describeCall>) => Response | undefined;

/** Answers the catalogue and the address; anything else goes to `extra`. */
function server(extra: Handler = () => undefined) {
  return (call: ApiCall): Response => {
    const c = describeCall(call);
    const answer = extra(c);
    if (answer) return answer;
    if (c.path === '/api/catalog/business-types') return Response.json(TYPES);
    if (c.path === '/api/hubs/address') return Response.json({ slug: 'pasteleria-dulce', host: 'pasteleria-dulce.localhost:8000' });
    return Response.json({});
  };
}

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  document.body.innerHTML = '';
});

async function setup(options: { props?: Record<string, unknown>; api?: Handler; locale?: 'en' | 'es' } = {}) {
  const created = vi.fn();
  const pending = ref(false);
  const form = ref<InstanceType<typeof BusinessCreateForm>>();
  const Host = {
    render: () =>
      h(BusinessCreateForm, {
        ref: form,
        ...options.props,
        onCreated: created,
        'onUpdate:pending': (value: boolean) => (pending.value = value),
      }),
  };
  const m = await mountHubs(Host, { api: server(options.api), locale: options.locale });
  await flush();
  const get = (id: string) => m.wrapper.get(`[data-testid="${id}"]`);
  /** Types in an Ionic field, as Ionic does (`ionInput` with its value). */
  async function type(id: string, value: string) {
    const el = get(id).element as HTMLElement & { value?: string };
    el.value = value;
    el.dispatchEvent(new CustomEvent('ionInput', { detail: { value } }));
    await flush();
  }
  async function pick(id: string, value: string) {
    get(id).element.dispatchEvent(new CustomEvent('ionChange', { detail: { value } }));
    await flush();
  }
  return { ...m, created, pending, form, get, type, pick };
}

const props = ionProps;

describe('BusinessCreateForm: the fields', () => {
  // flow: HUBS-F01 (HUBS-G65): the country comes suggested by the browser's languages.
  it("picks the country the browser's languages suggest", async () => {
    vi.spyOn(navigator, 'languages', 'get').mockReturnValue(['fr-BE', 'fr']);
    try {
      const s = await setup();
      expect((s.get('create-country').element as HTMLElement & { value?: string }).value).toBe('BE');
    } finally {
      vi.restoreAllMocks();
    }
  });

  it('asks the name, the country (Spain first picked) and an optional type, as outlined md fields', async () => {
    const s = await setup();
    const name = s.get('create-name');
    expect(name.element.tagName).toBe('ION-INPUT');
    expect(props(name, 'mode', 'fill', 'labelPlacement', 'autocomplete', 'label', 'required')).toEqual({
      mode: 'md',
      fill: 'outline',
      labelPlacement: 'floating',
      autocomplete: 'organization',
      label: 'Business name',
      required: true,
    });
    const country = s.get('create-country');
    expect(country.element.tagName).toBe('ION-SELECT');
    expect(props(country, 'mode', 'fill', 'interface', 'label')).toEqual({ mode: 'md', fill: 'outline', interface: 'popover', label: 'Country' });
    expect((country.element as HTMLElement & { value?: string }).value).toBe('ES');
    expect(country.findAll('ion-select-option')).toHaveLength(27);
    const type = s.get('create-type');
    expect(props(type, 'mode', 'fill', 'interface', 'label')).toEqual({
      mode: 'md',
      fill: 'outline',
      interface: 'popover',
      label: 'Business type (optional)',
    });
    expect(type.findAll('ion-select-option').map((o) => o.text())).toEqual(["I don't know yet", 'Bakery and pastry', 'Hair salon']);
    expect(s.get('create-type-hint').text()).toBe('With the type, your business is born with the modules of its sector. You can leave it blank.');
  });

  it('has no native select: only Ionic controls', async () => {
    const s = await setup();
    expect(s.wrapper.find('select').exists()).toBe(false);
    for (const input of s.wrapper.findAll('input:not([type="hidden"])')) {
      expect(input.element.closest('ion-input, ion-select')).not.toBeNull();
    }
  });

  it('keeps the form usable without the type catalogue, and says why it is missing', async () => {
    const s = await setup({ api: (c) => (c.path === '/api/catalog/business-types' ? apiError(503, 'unavailable', 'down') : undefined) });
    expect(s.get('create-type').findAll('ion-select-option').map((o) => o.text())).toEqual(["I don't know yet"]);
    expect(s.get('create-type-hint').text()).toBe('The business types could not be loaded right now. You can create the business without one.');
  });

  it('speaks Spanish, countries included', async () => {
    const s = await setup({ locale: 'es' });
    expect(props(s.get('create-name'), 'label')).toEqual({ label: 'Nombre del negocio' });
    expect(s.get('create-country').findAll('ion-select-option').find((o) => optionValue(o) === 'ES')?.text()).toBe('España');
    expect(s.get('create-submit').text()).toBe('Crear mi negocio');
  });
});

describe('BusinessCreateForm: the address it proposes', () => {
  it('asks for a free address 300 ms after the name stops changing, and shows it', async () => {
    const s = await setup();
    await s.type('create-name', 'Pastelería');
    await s.type('create-name', 'Pastelería Dulce');
    expect(s.get('create-address').text()).toBe('Finding a free address…');
    await s.clock.advance(300);
    await flush();
    const asked = s.calls().filter((c) => c.path === '/api/hubs/address');
    expect(asked.map((c) => c.query)).toEqual([{ name: 'Pastelería Dulce' }]);
    expect(s.get('create-address').text()).toBe('Your address will be pasteleria-dulce.localhost:8000');
  });

  it('shows no address without a name, nor when it could not be asked', async () => {
    const s = await setup({ api: (c) => (c.path === '/api/hubs/address' ? apiError(500, 'server_error', 'boom') : undefined) });
    expect(s.wrapper.find('[data-testid="create-address"]').exists()).toBe(false);
    await s.type('create-name', 'Bar');
    await s.clock.advance(300);
    await flush();
    expect(s.wrapper.find('[data-testid="create-address"]').exists()).toBe(false);
  });
});

describe('BusinessCreateForm: creating', () => {
  it('without a name says so on the field and asks nothing', async () => {
    const s = await setup();
    await s.get('create-submit').trigger('click');
    await flush();
    const name = s.get('create-name');
    expect(props(name, 'errorText')).toEqual({ errorText: 'Write the name of your business.' });
    expect(name.classes()).toEqual(expect.arrayContaining(['ion-invalid', 'ion-touched']));
    expect(s.calls().filter((c) => c.path === '/api/hubs/businesses')).toEqual([]);
  });

  it('creates the business with the name, the country and the type, says so and hands the business over', async () => {
    const s = await setup({ api: (c) => (c.path === '/api/hubs/businesses' ? Response.json(DETAIL, { status: 201 }) : undefined) });
    await s.type('create-name', '  Pastelería Dulce ');
    await s.pick('create-country', 'PT');
    await s.pick('create-type', 'bakery');
    await s.get('create-submit').trigger('click');
    await flush();
    const create = s.calls().find((c) => c.path === '/api/hubs/businesses');
    expect(create).toMatchObject({ method: 'POST', body: { name: 'Pastelería Dulce', country: 'PT', business_type: 'bakery' } });
    expect(s.created).toHaveBeenCalledWith(DETAIL, { typeName: 'Bakery and pastry' });
    expect(toastSuccess).toHaveBeenCalledWith('Business created: Pastelería Dulce');
  });

  it('sends no type when the person does not know it', async () => {
    const s = await setup({ api: (c) => (c.path === '/api/hubs/businesses' ? Response.json(DETAIL, { status: 201 }) : undefined) });
    await s.type('create-name', 'Bar');
    await s.get('create-submit').trigger('click');
    await flush();
    expect(s.calls().find((c) => c.path === '/api/hubs/businesses')?.body).toEqual({ name: 'Bar', country: 'ES', business_type: null });
    expect(s.created).toHaveBeenCalledWith(DETAIL, { typeName: null });
  });

  it('is busy while it creates: the button spins and is disabled, and the parent is told', async () => {
    let answer!: (r: Response) => void;
    const s = await setup({
      api: (c) => (c.path === '/api/hubs/businesses' ? (new Promise<Response>((r) => (answer = r)) as unknown as Response) : undefined),
    });
    await s.type('create-name', 'Bar');
    await s.get('create-submit').trigger('click');
    await flush();
    expect(s.pending.value).toBe(true);
    expect(props(s.get('create-submit'), 'disabled')).toEqual({ disabled: true });
    expect(s.get('create-submit').find('ion-spinner').exists()).toBe(true);
    answer(Response.json(DETAIL, { status: 201 }));
    await flush();
    expect(s.pending.value).toBe(false);
  });

  it("puts the server's field errors on their fields", async () => {
    const s = await setup({
      api: (c) =>
        c.path === '/api/hubs/businesses'
          ? apiError(422, 'invalid_payload', 'Invalid payload', { country: 'Choose one of the countries ERPlora serves.' })
          : undefined,
    });
    await s.type('create-name', 'Bar');
    await s.get('create-submit').trigger('click');
    await flush();
    expect(props(s.get('create-country'), 'errorText')).toEqual({ errorText: 'Choose one of the countries ERPlora serves.' });
    expect(s.get('create-country').classes()).toContain('ion-invalid');
    expect(s.created).not.toHaveBeenCalled();
  });

  it("says any other refusal above the button (one free business per account)", async () => {
    const s = await setup({
      api: (c) =>
        c.path === '/api/hubs/businesses'
          ? apiError(409, 'hubs.free_hub_limit', 'You already have a free business. Change its plan to create another one.')
          : undefined,
    });
    await s.type('create-name', 'Bar');
    await s.get('create-submit').trigger('click');
    await flush();
    expect(s.get('create-error').text()).toContain('You already have a free business. Change its plan to create another one.');
  });

  it('a lost connection is said in the person’s language', async () => {
    const s = await setup({ api: (c) => (c.path === '/api/hubs/businesses' ? (Promise.reject(new TypeError('Failed to fetch')) as never) : undefined) });
    await s.type('create-name', 'Bar');
    await s.get('create-submit').trigger('click');
    await flush();
    expect(s.get('create-error').text()).toContain('We could not reach ERPlora. Check your connection and try again.');
  });

  it('without its own button (inside a dialog) is submitted by the parent', async () => {
    const s = await setup({
      props: { submitButton: false },
      api: (c) => (c.path === '/api/hubs/businesses' ? Response.json(DETAIL, { status: 201 }) : undefined),
    });
    expect(s.wrapper.find('[data-testid="create-submit"]').exists()).toBe(false);
    await s.type('create-name', 'Bar');
    await s.form.value!.submit();
    await flush();
    expect(s.created).toHaveBeenCalledOnce();
  });
});
