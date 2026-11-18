/**
 * `fiscal.RepresentationState`: the state of a business's signed authorisation; `none` when it never sent one.
 */
export type RepresentationState = 'none' | 'submitted' | 'approved' | 'returned' | 'revoked';

/** `fiscal.RepresentationStatusIn`: the business. */
export interface RepresentationStatusIn {
  id: string;
}

/** `fiscal.RepresentationDocumentsOut`: which documents the authorisation carries (never the documents). */
export interface RepresentationDocumentsOut {
  signed_model: boolean;
  id_copy: boolean;
  signature_sample: boolean;
  representation_proof: boolean;
}

/** `fiscal.RepresentationHistoryOut`: one version sent; `superseded` when a newer one replaced it before any review. */
export interface RepresentationHistoryOut {
  version: number;
  status: 'submitted' | 'approved' | 'returned' | 'revoked';
  submitted_at: string;
  reviewed_at: string | null;
  reason: string;
  superseded: boolean;
}

/**
 * `fiscal.RepresentationStatusOut`: the authorisation in force if there is one, else the one waiting for review,
 * else the one that changed last; `changed_at` is when it last changed (sent, reviewed or withdrawn); `reason` is
 * the staff's note.
 */
export interface RepresentationStatusOut {
  status: RepresentationState;
  version: number | null;
  submitted_at: string | null;
  reviewed_at: string | null;
  changed_at: string | null;
  reason: string;
  taxpayer_tax_id: string;
  taxpayer_name: string;
  signer_name: string;
  documents: RepresentationDocumentsOut;
  history: RepresentationHistoryOut[];
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'fiscal.representation.status': { input: RepresentationStatusIn; output: RepresentationStatusOut };
  }
}
