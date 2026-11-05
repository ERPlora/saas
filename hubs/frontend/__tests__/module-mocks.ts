// The module doubles most tests of the businesses panel start with, written once. `vi.mock` is hoisted in each test
// file, so the file keeps its own call and hands the factory over (a factory cannot read the file's imports):
//   vi.mock('@ionic/vue', async (original) => (await import('../__tests__/module-mocks')).ionicWithModalStub(original));
//   vi.mock('@erplora/ui/shell', async (original) => (await import('../__tests__/module-mocks')).shellWithToastSpies(original));
// Only types are imported here: a real import of either module from inside its own factory would load it unmocked.
import { vi } from 'vitest';

type Original = <T>() => Promise<T>;

/** Ionic Vue with the ui's `IonModal` double: a FormModal or a ConfirmDialog presents itself outside a browser. */
export async function ionicWithModalStub(original: Original) {
  const { IonModalStub } = await import('./ion-modal-stub');
  return { ...(await original<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
}

/** The shell with its toasts spied on: what a page says once it did something. */
export async function shellWithToastSpies(original: Original) {
  return {
    ...(await original<typeof import('@erplora/ui/shell')>()),
    toastSuccess: vi.fn(() => Promise.resolve()),
    toastError: vi.fn(() => Promise.resolve()),
  };
}
