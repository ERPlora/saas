// Op → route map of the SaaS's API, for the SDK's API client (`createLiveClient(cfg, { routes })`).
// `operations.json` is written BY HAND for now, from the api.py of each app (base, accounts, hubs, apps, billing, fiscal); later it
// is generated (with the types of `../sdk-types.d.ts`) from `/api/openapi.json`, as in hub-next.
import { parseOperationRoutes } from '@erplora/ui/sdk';

import operations from './operations.json';

export const OPERATION_ROUTES = parseOperationRoutes(operations);
