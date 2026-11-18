// hubs (hubs/schemas/): what creates, changes, deletes or opens a business.
import type { BusinessDetailOut, ByIdIn } from './hubs';

/** `hubs.AddressProposeIn`. */
export interface AddressProposeIn {
  name: string;
}

/** `hubs.AddressProposeOut`. */
export interface AddressProposeOut {
  slug: string;
  host: string;
}

/** `hubs.BusinessCreateIn`: a name, a country, and a business type if the person knows. */
export interface BusinessCreateIn {
  name: string;
  country: string;
  business_type?: string | null;
  slug?: string | null;
}

/** `hubs.BusinessUpdateIn`: only the fields sent change. */
export interface BusinessUpdateIn {
  id: string;
  name?: string;
  country?: string;
  language?: 'en' | 'es';
  timezone?: string;
}

/** `hubs.BusinessAddressIn`: the new web address of the business (HUBS-F16). */
export interface BusinessAddressIn {
  id: string;
  slug: string;
}

/** `hubs.BusinessDeleteIn`. */
export interface BusinessDeleteIn {
  id: string;
  confirm_name: string;
}

/** `hubs.BusinessOpenIn`. */
export interface BusinessOpenIn {
  id: string;
  next?: string;
  /** Inside the installed app: the jump carries `shell=1`, with which the app links the till to the business. */
  shell?: boolean;
}

/** `hubs.BusinessOpenOut`: where «Open» goes, the Hub's start of the jump (`/auth/login?next=`), which
 *  binds it to the browser with its own `state`. The SPA navigates there. */
export interface BusinessOpenOut {
  url: string;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'hubs.business.create': { input: BusinessCreateIn; output: BusinessDetailOut };
    'hubs.business.get': { input: ByIdIn; output: BusinessDetailOut };
    'hubs.business.check': { input: ByIdIn; output: BusinessDetailOut };
    'hubs.business.update': { input: BusinessUpdateIn; output: BusinessDetailOut };
    'hubs.business.change_address': { input: BusinessAddressIn; output: BusinessDetailOut };
    'hubs.business.delete': { input: BusinessDeleteIn; output: BusinessDetailOut };
    'hubs.business.restore': { input: ByIdIn; output: BusinessDetailOut };
    'hubs.business.open': { input: BusinessOpenIn; output: BusinessOpenOut };
    'hubs.address.propose': { input: AddressProposeIn; output: AddressProposeOut };
  }
}
