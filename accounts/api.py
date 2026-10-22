"""Ninja routes of accounts: each route calls exactly one operation and holds no logic.

Sign-in is not here: it is allauth.headless's API at ``/_allauth/`` (and Google at its own paths). No
operation here is exposed to API keys: a key never manages the account (``api_auth``). Ids travel in the
input, never in the path (one parameter per route, the operation's input), as in hubs.
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from accounts import queries, services
from accounts.schemas import (
    ApiKeyCreateIn,
    ApiKeyRevokeIn,
    EmailChangeIn,
    EmailVerifyIn,
    PhotoUploadIn,
    PreferencesUpdateIn,
    ProfileUpdateIn,
    SessionCloseIn,
    SessionListIn,
    SupportReportIn,
)

router = Router(tags=["accounts"])


# Session auth (the API's default): an anonymous visitor gets the 401 envelope.
@bind(router, "accounts.hub.list", "/accounts/hubs")
async def hub_list(request):
    return await run_operation(request, queries.hub_list)


# --- The Account page (plan 2026-10-13, L3-A) ---------------------------------------------------------------


@bind(router, "accounts.profile.get", "/accounts/profile")
async def profile_get(request):
    return await run_operation(request, queries.profile_get)


@bind(router, "accounts.profile.update", "/accounts/profile")
async def profile_update(request, data: ProfileUpdateIn):
    return await run_operation(request, services.profile_update, data)


@bind(router, "accounts.profile.delete", "/accounts/profile/delete")
async def profile_delete(request):
    return await run_operation(request, services.profile_delete)


@bind(router, "accounts.data.export", "/accounts/export")
async def data_export(request):
    return await run_operation(request, queries.data_export)


@bind(router, "accounts.email.change", "/accounts/email/change")
async def email_change(request, data: EmailChangeIn):
    return await run_operation(request, services.email_change, data)


@bind(router, "accounts.email.verify", "/accounts/email/verify")
async def email_verify(request, data: EmailVerifyIn):
    return await run_operation(request, services.email_verify, data)


@bind(router, "accounts.photo.upload", "/accounts/photo")
async def photo_upload(request, data: PhotoUploadIn):
    return await run_operation(request, services.photo_upload, data)


@bind(router, "accounts.photo.remove", "/accounts/photo/remove")
async def photo_remove(request):
    return await run_operation(request, services.photo_remove)


@bind(router, "accounts.preferences.get", "/accounts/preferences")
async def preferences_get(request):
    return await run_operation(request, queries.preferences_get)


@bind(router, "accounts.preferences.update", "/accounts/preferences")
async def preferences_update(request, data: PreferencesUpdateIn):
    return await run_operation(request, services.preferences_update, data)


@bind(router, "accounts.session.list", "/accounts/sessions")
async def session_list(request, params: Query[SessionListIn]):
    return await run_operation(request, queries.session_list, params)


@bind(router, "accounts.session.close", "/accounts/sessions/close")
async def session_close(request, data: SessionCloseIn):
    return await run_operation(request, services.session_close, data)


@bind(router, "accounts.session.close_others", "/accounts/sessions/close_others")
async def session_close_others(request):
    return await run_operation(request, services.session_close_others)


@bind(router, "accounts.browser_trust.get", "/accounts/browser-trust")
async def browser_trust_get(request):
    return await run_operation(request, queries.browser_trust_get)


@bind(router, "accounts.browser_trust.revoke", "/accounts/browser-trust/revoke")
async def browser_trust_revoke(request):
    return await run_operation(request, services.browser_trust_revoke)


@bind(router, "accounts.apikey.list", "/accounts/api-keys")
async def apikey_list(request):
    return await run_operation(request, queries.apikey_list)


@bind(router, "accounts.apikey.create", "/accounts/api-keys", status=201)
async def apikey_create(request, data: ApiKeyCreateIn):
    return await run_operation(request, services.apikey_create, data)


@bind(router, "accounts.apikey.revoke", "/accounts/api-keys/revoke")
async def apikey_revoke(request, data: ApiKeyRevokeIn):
    return await run_operation(request, services.apikey_revoke, data)


@bind(router, "accounts.support.report", "/accounts/support/report")
async def support_report(request, data: SupportReportIn):
    return await run_operation(request, services.support_report, data)
