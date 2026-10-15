// The authorisation for ERPlora to file a business's invoices with the AEAT, on the business's Summary: the live
// `fiscal.representation.status` (owner and admins), its state in plain words (a pill and a line), what the
// business sent and what is missing, the history of its submissions, and «Manage in your business» (the upload
// and the signature are the Hub's: VeriFactu → Settings). Loading: a skeleton; a failure: `LoadFailed`.
import { formatDateTime } from '@erplora/ui/components';
import { afterEach, describe, expect, it } from 'vitest';

import { errorFrame, flush, mountHubs, subId } from '../../../hubs/frontend/__tests__/mount-hubs';
import RepresentationCard from './RepresentationCard.vue';

const OP = 'fiscal.representation.status';

const NO_DOCUMENTS = { signed_model: false, id_copy: false, signature_sample: false, representation_proof: false };
const NONE = {
  status: 'none',
  version: null,
  submitted_at: null,
  reviewed_at: null,
  changed_at: null,
  reason: '',
  taxpayer_tax_id: '',
  taxpayer_name: '',
  signer_name: '',
  documents: NO_DOCUMENTS,
  history: [],
};
const SENT_AT = '2026-10-10T09:30:00Z';
const REVIEWED_AT = '2026-10-12T16:05:00Z';
// A withdrawal comes days after the approval: its line says when it was withdrawn, never when it was approved.
const WITHDRAWN_AT = '2026-10-14T11:20:00Z';
const SUBMITTED = {
  ...NONE,
  status: 'submitted',
  version: 1,
  submitted_at: SENT_AT,
  changed_at: SENT_AT,
  taxpayer_tax_id: 'B12345678',
  taxpayer_name: 'Panadería López SL',
  signer_name: 'Laura Martín',
  documents: { signed_model: true, id_copy: true, signature_sample: false, representation_proof: true },
  history: [{ version: 1, status: 'submitted', submitted_at: SENT_AT, reviewed_at: null, reason: '', superseded: false }],
};
const APPROVED = { ...SUBMITTED, status: 'approved', reviewed_at: REVIEWED_AT, changed_at: REVIEWED_AT };
const RETURNED = {
  ...SUBMITTED,
  status: 'returned',
  reviewed_at: REVIEWED_AT,
  changed_at: REVIEWED_AT,
  reason: 'The signature does not match the ID.',
};
const REVOKED = { ...SUBMITTED, status: 'revoked', reviewed_at: REVIEWED_AT, changed_at: WITHDRAWN_AT, reason: '' };

afterEach(() => {
  document.body.innerHTML = '';
});

async function setup(data: Record<string, unknown> | null, locale: 'en' | 'es' = 'en', props: Record<string, unknown> = {}) {
  const m = await mountHubs(RepresentationCard, { props: { id: 'h1', canManage: true, ...props }, locale });
  const call = await m.live();
  if (data) await m.result(call, OP, data);
  const testid = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  return { ...m, call, testid };
}

describe('RepresentationCard: the query', () => {
  it('follows fiscal.representation.status of the business', async () => {
    const s = await setup(NONE);
    expect(s.client.stream.subscriptions(OP).map((sub) => sub.params)).toEqual([{ id: 'h1' }]);
  });

  it('is titled by what it is, in both languages', async () => {
    expect((await setup(NONE)).wrapper.find('h2').text()).toBe('Authorisation for ERPlora to file your invoices');
    expect((await setup(NONE, 'es')).wrapper.find('h2').text()).toBe('Autorización para que ERPlora remita tus facturas');
  });

  it('loading: a skeleton, no state yet', async () => {
    const s = await setup(null);
    expect(s.testid('representation-loading').exists()).toBe(true);
    expect(s.testid('representation-pill').exists()).toBe(false);
  });

  it('a failure: why, and «Retry»', async () => {
    const s = await setup(null);
    s.call.push(errorFrame(subId(s.client, OP), 'not_found'));
    await flush();
    expect(s.testid('representation-loading').exists()).toBe(false);
    expect(s.testid('representation-error').text()).toContain('We could not load the authorisation');
    expect(s.testid('representation-retry').exists()).toBe(true);
  });

  it('a role that may not see it: no permission, not a connection problem, no «Retry»', async () => {
    const s = await setup(null, 'es');
    s.call.push(errorFrame(subId(s.client, OP), 'permission_denied'));
    await flush();
    expect(s.testid('representation-error').text()).toContain('No tienes permiso para ver la autorización');
    expect(s.testid('representation-retry').exists()).toBe(false);
  });
});

describe('RepresentationCard: each state in plain words', () => {
  const cases: Array<[string, 'en' | 'es', Record<string, unknown>, string, string]> = [
    [
      'none',
      'en',
      NONE,
      'Not granted',
      'You have not signed the authorisation yet. Download the official model, sign it and upload it from your business (VeriFactu → Settings).',
    ],
    [
      'none',
      'es',
      NONE,
      'Sin otorgar',
      'Todavía no has firmado la autorización. Descarga el modelo oficial, fírmalo y súbelo desde tu negocio (VeriFactu → Configuración).',
    ],
    ['submitted', 'en', SUBMITTED, 'Under review', 'We are reviewing your authorisation. It usually takes between 24 and 72 hours.'],
    ['submitted', 'es', SUBMITTED, 'En revisión', 'Estamos revisando tu autorización. Suele tardar entre 24 y 72 horas.'],
    [
      'approved',
      'en',
      APPROVED,
      'Approved',
      `Validated on ${formatDateTime(REVIEWED_AT, 'en')}. ERPlora can file your invoices with the AEAT on your behalf.`,
    ],
    [
      'approved',
      'es',
      APPROVED,
      'Validada',
      `Validada el ${formatDateTime(REVIEWED_AT, 'es')}. ERPlora puede remitir tus facturas a la AEAT en tu nombre.`,
    ],
    [
      'returned',
      'en',
      RETURNED,
      'Returned',
      'We could not accept the authorisation you sent. Fix what we tell you and upload it again from your business.',
    ],
    [
      'returned',
      'es',
      RETURNED,
      'Devuelta',
      'No hemos podido aceptar la autorización que enviaste. Corrige lo que te indicamos y vuelve a subirla desde tu negocio.',
    ],
    [
      'revoked',
      'en',
      REVOKED,
      'Withdrawn',
      `The authorisation was withdrawn on ${formatDateTime(WITHDRAWN_AT, 'en')}. Sign a new one from your business to keep filing through ERPlora.`,
    ],
    [
      'revoked',
      'es',
      REVOKED,
      'Retirada',
      `La autorización se retiró el ${formatDateTime(WITHDRAWN_AT, 'es')}. Firma una nueva desde tu negocio para seguir remitiendo con ERPlora.`,
    ],
  ];

  it.each(cases)('%s (%s): the pill and the line', async (_status, locale, data, pill, line) => {
    const s = await setup(data, locale);
    expect(s.testid('representation-pill').text()).toBe(pill);
    expect(s.testid('representation-line').text()).toBe(line);
  });

  it('gives each state its tone: fine, in progress, failed, needs attention, inert', async () => {
    const tones: Record<string, string> = {};
    for (const data of [NONE, SUBMITTED, APPROVED, RETURNED, REVOKED]) {
      const s = await setup(data);
      tones[data.status] = s.testid('representation-pill').attributes('data-tone')!;
      s.wrapper.unmount();
    }
    expect(tones).toEqual({ none: 'neutral', submitted: 'info', approved: 'success', returned: 'danger', revoked: 'warning' });
  });

  it('submitted: says when it was sent', async () => {
    expect((await setup(SUBMITTED)).testid('representation-sent').text()).toBe(`Sent on ${formatDateTime(SENT_AT, 'en')}`);
    expect((await setup(SUBMITTED, 'es')).testid('representation-sent').text()).toBe(`Enviada el ${formatDateTime(SENT_AT, 'es')}`);
  });

  it('returned: says why, under its own heading', async () => {
    const s = await setup(RETURNED);
    expect(s.testid('representation-reason').find('h3').text()).toBe('Why it was returned');
    expect(s.testid('representation-reason').text()).toContain('The signature does not match the ID.');
    const es = await setup(RETURNED, 'es');
    expect(es.testid('representation-reason').find('h3').text()).toBe('Por qué se devolvió');
  });

  it('revoked: the reason only when there is one', async () => {
    expect((await setup(REVOKED)).testid('representation-reason').exists()).toBe(false);
    const s = await setup({ ...REVOKED, reason: 'The company changed its administrator.' });
    expect(s.testid('representation-reason').find('h3').text()).toBe('Why it was withdrawn');
    expect(s.testid('representation-reason').text()).toContain('The company changed its administrator.');
  });

  it('says whose it is and who signed it, once there is one', async () => {
    const s = await setup(SUBMITTED);
    expect(s.testid('representation-taxpayer').text()).toContain('Panadería López SL (B12345678)');
    expect(s.testid('representation-signer').text()).toContain('Laura Martín');
    expect((await setup(NONE)).testid('representation-taxpayer').exists()).toBe(false);
  });
});

describe('RepresentationCard: what was sent and what is missing', () => {
  it('lists only the documents received, each with a tick', async () => {
    const s = await setup(SUBMITTED);
    const received = s.testid('representation-received');
    expect(received.find('h3').text()).toBe('What you sent');
    expect(received.findAll('li').map((li) => li.text())).toEqual([
      'Signed model',
      'Copy of the identity document',
      'Proof of representation',
    ]);
    // The tick is decoration: the list already says it was received.
    expect(received.findAll('li .tick').map((tick) => tick.attributes('aria-hidden'))).toEqual(['true', 'true', 'true']);
  });

  it('in Spanish too', async () => {
    const s = await setup({ ...SUBMITTED, documents: { ...SUBMITTED.documents, signature_sample: true } }, 'es');
    expect(s.testid('representation-received').find('h3').text()).toBe('Lo que has enviado');
    expect(s.testid('representation-received').findAll('li').map((li) => li.text())).toEqual([
      'Modelo firmado',
      'Copia del documento de identidad',
      'Muestra de firma',
      'Acreditación de la representación',
    ]);
  });

  it('none: nothing sent; missing, the two required documents', async () => {
    const s = await setup(NONE);
    expect(s.testid('representation-received').exists()).toBe(false);
    expect(s.testid('representation-missing').find('h3').text()).toBe('What is missing');
    expect(s.testid('representation-missing').findAll('li').map((li) => li.text())).toEqual([
      'Signed model',
      'Copy of the identity document',
    ]);
    const es = await setup(NONE, 'es');
    expect(es.testid('representation-missing').find('h3').text()).toBe('Qué falta');
  });

  it('returned or withdrawn: missing, a new submission', async () => {
    for (const data of [RETURNED, REVOKED]) {
      const s = await setup(data);
      expect(s.testid('representation-missing').findAll('li').map((li) => li.text())).toEqual(['A new submission']);
      s.wrapper.unmount();
    }
    expect((await setup(RETURNED, 'es')).testid('representation-missing').findAll('li').map((li) => li.text())).toEqual([
      'Un envío nuevo',
    ]);
  });

  it('under review or approved: nothing missing', async () => {
    expect((await setup(SUBMITTED)).testid('representation-missing').exists()).toBe(false);
    expect((await setup(APPROVED)).testid('representation-missing').exists()).toBe(false);
  });
});

describe('RepresentationCard: the history of submissions', () => {
  const HISTORY = [
    { version: 4, status: 'submitted', submitted_at: '2026-10-14T08:00:00Z', reviewed_at: null, reason: '', superseded: false },
    { version: 3, status: 'returned', submitted_at: '2026-10-13T08:00:00Z', reviewed_at: null, reason: '', superseded: true },
    { version: 2, status: 'returned', submitted_at: '2026-10-12T08:00:00Z', reviewed_at: REVIEWED_AT, reason: 'Blurry ID.', superseded: false },
    { version: 1, status: 'approved', submitted_at: '2026-10-01T08:00:00Z', reviewed_at: REVIEWED_AT, reason: '', superseded: false },
    { version: 0, status: 'revoked', submitted_at: '2026-09-01T08:00:00Z', reviewed_at: REVIEWED_AT, reason: '', superseded: false },
  ];
  const WITHDRAWN = {
    version: 0,
    status: 'revoked',
    submitted_at: '2026-09-01T08:00:00Z',
    reviewed_at: REVIEWED_AT,
    reason: 'The company changed its administrator.',
    superseded: false,
  };

  it('one submission: no history', async () => {
    expect((await setup(SUBMITTED)).testid('representation-history').exists()).toBe(false);
  });

  it('two or more: #version · date · what became of it', async () => {
    const s = await setup({ ...APPROVED, history: HISTORY });
    expect(s.testid('representation-history').find('h3').text()).toBe('Submission history');
    expect(s.testid('representation-history').findAll('li').map((li) => li.text())).toEqual([
      `#4 · ${formatDateTime(HISTORY[0].submitted_at, 'en')} · Under review`,
      `#3 · ${formatDateTime(HISTORY[1].submitted_at, 'en')} · Replaced by a newer submission`,
      `#2 · ${formatDateTime(HISTORY[2].submitted_at, 'en')} · Returned: Blurry ID.`,
      `#1 · ${formatDateTime(HISTORY[3].submitted_at, 'en')} · Approved`,
      `#0 · ${formatDateTime(HISTORY[4].submitted_at, 'en')} · Withdrawn`,
    ]);
  });

  it('a withdrawn one says why, in both languages', async () => {
    const history = [HISTORY[2], WITHDRAWN];
    const s = await setup({ ...REVOKED, history });
    expect(s.testid('representation-history').findAll('li').map((li) => li.text())).toEqual([
      `#2 · ${formatDateTime(HISTORY[2].submitted_at, 'en')} · Returned: Blurry ID.`,
      `#0 · ${formatDateTime(WITHDRAWN.submitted_at, 'en')} · Withdrawn: The company changed its administrator.`,
    ]);
    const es = await setup({ ...REVOKED, history }, 'es');
    expect(es.testid('representation-history').findAll('li').map((li) => li.text())[1]).toBe(
      `#0 · ${formatDateTime(WITHDRAWN.submitted_at, 'es')} · Retirada: The company changed its administrator.`,
    );
  });

  it('in Spanish, and a returned one without a reason says only that', async () => {
    const history = [HISTORY[1], { ...HISTORY[2], reason: '' }];
    const s = await setup({ ...RETURNED, history }, 'es');
    expect(s.testid('representation-history').find('h3').text()).toBe('Historial de envíos');
    expect(s.testid('representation-history').findAll('li').map((li) => li.text())).toEqual([
      `#3 · ${formatDateTime(HISTORY[1].submitted_at, 'es')} · Sustituida por un envío más reciente`,
      `#2 · ${formatDateTime(HISTORY[2].submitted_at, 'es')} · Devuelta`,
    ]);
  });
});

describe('RepresentationCard: «Manage in your business»', () => {
  it('asks the page to open the business (the upload is the Hub’s)', async () => {
    const s = await setup(NONE);
    const button = s.testid('representation-manage');
    expect(button.text()).toBe('Manage in your business');
    expect(button.attributes('disabled')).toBeUndefined();
    await button.trigger('click');
    expect(s.wrapper.emitted('manage')).toHaveLength(1);
    expect((await setup(NONE, 'es')).testid('representation-manage').text()).toBe('Gestionar en tu negocio');
  });

  it('busy while the business opens; gone when it cannot be opened', async () => {
    const busy = await setup(NONE, 'en', { managing: true });
    expect(busy.testid('representation-manage').attributes('disabled')).toBeDefined();
    expect((await setup(NONE, 'en', { canManage: false })).testid('representation-manage').exists()).toBe(false);
  });
});
