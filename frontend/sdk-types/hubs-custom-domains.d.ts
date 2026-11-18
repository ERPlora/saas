import type { ByIdIn } from './hubs';

/** `hubs.CustomDomainRequestIn`: a business and the domain its owner wants for its public website, as typed (HUBS-F17). */
export interface CustomDomainRequestIn {
  id: string;
  domain: string;
}

/** `hubs.DnsRecordOut`: a record the owner creates at their domain provider. */
export interface DnsRecordOut {
  type: string;
  name: string;
  value: string;
}

/** `CustomDomain.State` of hubs/models/custom_domains.py: on its way, served, not served, or being removed by its owner. */
export type CustomDomainState = 'pending' | 'active' | 'lapsed' | 'removing';

/** `CustomDomain.Reason` of hubs/models/custom_domains.py: where a domain is stuck; empty when nothing is missing. */
export type CustomDomainReason =
  | ''
  | 'certificate_pending'
  | 'certificate_unavailable'
  | 'certificate_failed'
  | 'validation_timed_out'
  | 'quota_full'
  | 'cname_missing'
  | 'dns_unavailable'
  | 'probe_failed'
  | 'taken'
  | 'checks_failed'
  | 'not_in_plan'
  | 'business_gone';

/** `hubs.CustomDomainOut`: a business's own domain, its two records and what is missing, in the person's words. */
export interface CustomDomainOut {
  id: string;
  domain: string;
  state: CustomDomainState;
  state_label: string;
  reason: CustomDomainReason;
  reason_label: string;
  /** Validates the certificate and renews it; `null` for the few seconds until ACM has it. */
  validation: DnsRecordOut | null;
  /** Takes the visits to ERPlora: created once the certificate is ready. */
  traffic: DnsRecordOut;
  failures: number;
  checked_at: string | null;
  activated_at: string | null;
}

/** `hubs.CustomDomainStatusOut`: whether this deployment connects domains, whether the plan includes one, and the one there is. */
export interface CustomDomainStatusOut {
  available: boolean;
  in_plan: boolean;
  domain: CustomDomainOut | null;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'hubs.custom_domain.get': { input: ByIdIn; output: CustomDomainStatusOut };
    'hubs.custom_domain.request': { input: CustomDomainRequestIn; output: CustomDomainOut };
    'hubs.custom_domain.remove': { input: ByIdIn; output: CustomDomainStatusOut };
  }
}
