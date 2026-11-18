/** `hubs.DataCopyListIn` / `hubs.DataCopyLinkIn`: the copies of a business's data. */
export interface DataCopyListIn {
  business_id: string;
}

export interface DataCopyLinkIn {
  business_id: string;
  copy_id: string;
}

/** `hubs.DataCopyOut`: a full copy of the business's data the Hub keeps, made when it was deleted (`offboarding`) or
 *  before its data was reset (`reset`); its link is asked on each click. */
export interface DataCopyOut {
  id: string;
  kind: 'offboarding' | 'reset';
  created_at: string;
  bytes: number;
}

export interface DataCopyListOut {
  business_id: string;
  /** False: the business has no database of its own, so it never gets a copy. */
  available: boolean;
  /** Newest first; empty while the Hub has none yet (or is away). */
  copies: DataCopyOut[];
}

/** `hubs.DataCopyLinkOut`: a link of the Hub's that lasts 15 minutes. */
export interface DataCopyLinkOut {
  url: string;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'hubs.data_copy.list': { input: DataCopyListIn; output: DataCopyListOut };
    'hubs.data_copy.link': { input: DataCopyLinkIn; output: DataCopyLinkOut };
  }
}
