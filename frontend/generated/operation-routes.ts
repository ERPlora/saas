// Op → route map of the SaaS's API, for the SDK's API client (`createLiveClient(cfg, { routes })`).
// `operations.json` is written by hand, from the api.py of each app (base, accounts, hubs, apps, billing, fiscal).
import { parseOperationRoutes } from '@erplora/ui/sdk';

import operations from './operations.json';

export const OPERATION_ROUTES = parseOperationRoutes(operations);
