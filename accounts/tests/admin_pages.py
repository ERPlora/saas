"""What the account's page of the admin posts back, for the tests that save it: the admin's and the audit trail's."""


def _change_page(client, user):
    return client.get(f"/admin/accounts/user/{user.pk}/change/")


def _as_posted(page, **changes) -> dict:
    """What the account's page posts back as it stands, with ``changes`` (``False`` unticks a box): its editable
    fields and the management forms of its inlines."""
    form = page.context["adminform"].form
    data = {}
    for name, field in form.fields.items():
        value = form[name].value()
        if not field.disabled and value not in (None, False, "", []):
            data[name] = "on" if value is True else value
    for inline in page.context["inline_admin_formsets"]:
        management = inline.formset.management_form
        data.update({management.add_prefix(name): management[name].value() for name in management.fields})
    data.update(changes)
    return {name: value for name, value in data.items() if value is not False}
