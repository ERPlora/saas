// The ConfirmDialog a billing dialog is built on, as its tests read it: the component and one of its props.
import { ConfirmDialog } from '@erplora/ui/components';
import type { VueWrapper } from '@vue/test-utils';
import type { Component } from 'vue';

export function confirmDialogOf(wrapper: VueWrapper) {
  const dialog = () => wrapper.findComponent(ConfirmDialog as unknown as Component);
  const dialogProp = (name: string) => (dialog().props() as Record<string, unknown>)[name];
  return { dialog, dialogProp };
}
