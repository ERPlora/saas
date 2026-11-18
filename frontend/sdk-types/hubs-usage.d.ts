// hubs (hubs/schemas/ `*Usage*`): the usage of a business. A day travels as `YYYY-MM-DD` (UTC).

/** `hubs.StorageUsageOut`: the files (S3) against the space of the plan; `null` limit and percent without a plan. */
export interface StorageUsageOut {
  used_bytes: number;
  limit_bytes: number | null;
  /** Rounded; over 100 past the space of the plan. */
  percent: number | null;
}

/** `hubs.ActiveUsersOut`: the people active on the day measured and in the 30 days up to it. */
export interface ActiveUsersOut {
  on_day: number;
  last_30_days: number;
}

/** `hubs.UsageOut`: the last day the Hub measured; `stale` when it is not yesterday's (UTC). */
export interface UsageOut {
  day: string;
  storage: StorageUsageOut;
  active_users: ActiveUsersOut;
  stale: boolean;
}

/** `hubs.UsageGetIn`. */
export interface UsageGetIn {
  business_id: string;
}

/** `hubs.UsageSeriesIn`: the window, 1 to 365 days up to yesterday (30 by default). */
export interface UsageSeriesIn {
  business_id: string;
  days?: number;
}

/** `hubs.UsagePointOut`: one day measured of the window. */
export interface UsagePointOut {
  day: string;
  storage: StorageUsageOut;
  active_users: ActiveUsersOut;
}

/** `hubs.UsageSeriesOut`: the days measured of the window, oldest first, against the space of the plan today. */
export interface UsageSeriesOut {
  business_id: string;
  limit_bytes: number | null;
  points: UsagePointOut[];
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'hubs.usage.get': { input: UsageGetIn; output: UsageOut };
    'hubs.usage.series': { input: UsageSeriesIn; output: UsageSeriesOut };
  }
}
