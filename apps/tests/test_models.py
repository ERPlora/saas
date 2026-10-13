"""Models of apps: the shared catalog and ``Module`` (spec §3.2, §5.4 and §5.5; PLAN-SAAS §2.6).

``App`` and ``AppDoc`` concrete ``live.shared_catalog`` in the ``shared`` schema, written by the
Hub; ``Module`` is only what the SaaS sells of a paid app, tied to its app by ``slug`` without a
database FK: ``Module.clean()`` and the database check ``apps.E001`` keep it honest. The admin
shows the catalog read-only and ``Module`` with its validation.
"""

from unittest import mock

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core import checks
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.db.migrations.recorder import MigrationRecorder
from django.test import RequestFactory
from django.utils import translation
from live.shared_catalog import APP_DOC_TABLE, APP_TABLE, AbstractApp, AbstractAppDoc

from apps.checks import check_module_slugs
from apps.models import App, AppDoc, Module
from apps.tests.factories import make_app, make_doc

pytestmark = pytest.mark.django_db

HOST = "localhost"


# --- App and AppDoc: the contract of live.shared_catalog, concrete in its owner ------------------


def test_app_and_app_doc_concrete_the_shared_contract():
    assert issubclass(App, AbstractApp)
    assert issubclass(AppDoc, AbstractAppDoc)
    assert (App._meta.db_table, AppDoc._meta.db_table) == (APP_TABLE, APP_DOC_TABLE)
    assert APP_TABLE == '"shared"."app"'
    # The SaaS owns the tables and migrates them; the Hub's mirror is the one with managed = False.
    assert App._meta.managed and AppDoc._meta.managed
    assert App._meta.ordering == ["id"]
    assert AppDoc._meta.get_field("app").related_model is App


def test_one_doc_per_app_and_language():
    app = make_app("inventory")
    make_doc(app, "es")
    make_doc(app, "en")

    with pytest.raises(IntegrityError), transaction.atomic():
        make_doc(app, "es")
    assert [constraint.name for constraint in AppDoc._meta.constraints] == [
        "shared_app_doc_app_lang_unique"
    ]
    assert sorted(app.docs.values_list("lang", flat=True)) == ["en", "es"]


# --- Module: only commercial ---------------------------------------------------------------------


def test_module_holds_only_what_the_saas_sells():
    """Name, texts, icon, category and documentation come from shared.app (spec decision 7)."""
    assert {field.name for field in Module._meta.get_fields()} == {
        "id",
        "slug",
        "tier",
        "price_monthly_cents",
        "price_annual_cents",
        "stripe_product_id",
        "stripe_price_id_monthly",
        "stripe_price_id_annual",
        "is_active",
        "created_at",
        "updated_at",
    }
    # In the SaaS's own schema (public), not in shared: the Hub never sees it.
    assert Module._meta.db_table == "apps_module"


def test_module_key_is_a_uuid7_and_its_slug_is_unique():
    make_app("whatsapp_inbox", premium=True)
    module = Module.objects.create(slug="whatsapp_inbox")

    assert module.pk.version == 7
    with pytest.raises(IntegrityError), transaction.atomic():
        Module.objects.create(slug="whatsapp_inbox")


def test_prices_are_whole_cents_never_negative():
    """Stripe charges in the minor unit (an integer of cents): no float and no rounding here."""
    for name in ("price_monthly_cents", "price_annual_cents"):
        assert isinstance(Module._meta.get_field(name), models.PositiveIntegerField)
    make_app("whatsapp_inbox", premium=True)

    with pytest.raises(ValidationError) as error:
        Module(slug="whatsapp_inbox", price_monthly_cents=-1).full_clean()

    assert set(error.value.error_dict) == {"price_monthly_cents"}


def test_tier_is_the_lowest_plan_level_that_includes_the_module():
    """The levels of ADR-0474, the same names as ``Plan.included_level``; by default every paid plan."""
    assert Module.Tier.values == ["free", "basic", "pro", "enterprise"]
    assert Module().tier == Module.Tier.BASIC


# --- Module.clean(): the slug is a premium app of shared.app (spec §5.4) -------------------------


def slug_errors(module: Module) -> list[str]:
    with pytest.raises(ValidationError) as error:
        module.full_clean()
    return [item.code for item in error.value.error_dict["slug"]]


def test_clean_refuses_a_slug_that_is_not_in_the_catalog():
    assert slug_errors(Module(slug="ghost")) == ["unknown_app"]


def test_clean_refuses_a_free_app():
    """A free app (premium = False) is always entitled: it never has a Module row (PLAN-SAAS §2.6)."""
    make_app("inventory", premium=False)

    assert slug_errors(Module(slug="inventory")) == ["free_app"]


def test_clean_accepts_a_premium_app():
    make_app("whatsapp_inbox", premium=True)

    Module(slug="whatsapp_inbox").full_clean()


def test_clean_accepts_a_retired_premium_app():
    """A retired app (listed = False) still exists in shared.app: its Module row is not dangling."""
    make_app("whatsapp_inbox", premium=True, listed=False)

    Module(slug="whatsapp_inbox").full_clean()


def test_clean_refuses_a_slug_that_is_not_an_app_label():
    """The slug is the label of the app (= its folder in the Hub, spec §3.1)."""
    assert "invalid" in slug_errors(Module(slug="WhatsApp-Inbox"))


def test_clean_speaks_the_language_of_the_admin():
    make_app("inventory", premium=False)

    with pytest.raises(ValidationError) as unknown:
        Module(slug="ghost").full_clean()
    with pytest.raises(ValidationError) as free:
        Module(slug="inventory").full_clean()

    # Lazy messages: translated when they are read, as the admin form reads them.
    with translation.override("es"):
        assert unknown.value.message_dict["slug"] == [
            "No hay ninguna app «ghost» en el catálogo: el Hub registra sus apps al arrancar."
        ]
        assert free.value.message_dict["slug"] == [
            "La app «inventory» es gratuita: solo una app de pago (premium) se vende como módulo."
        ]


# --- Check apps.E001: every Module.slug exists in shared.app (spec §5.4) -------------------------


def test_e001_reports_a_module_whose_app_does_not_exist():
    """A data load or a script skips clean(): the database check catches it."""
    make_app("whatsapp_inbox", premium=True)
    Module.objects.create(slug="whatsapp_inbox")
    Module.objects.create(slug="ghost")

    errors = check_module_slugs(app_configs=None, databases=["default"])

    assert [error.id for error in errors] == ["apps.E001"]
    assert errors[0].level == checks.ERROR
    assert "ghost" in errors[0].msg
    assert "whatsapp_inbox" not in errors[0].msg


def test_e001_is_silent_when_every_module_has_its_app():
    make_app("whatsapp_inbox", premium=True, listed=False)
    Module.objects.create(slug="whatsapp_inbox")

    assert check_module_slugs(app_configs=None, databases=["default"]) == []


def test_e001_only_runs_against_the_database():
    """A plain ``check`` (no ``--database``) does not query: database checks need it named."""
    Module.objects.create(slug="ghost")

    assert check_module_slugs(app_configs=None, databases=None) == []


def test_e001_waits_for_the_migrations_of_apps():
    """``migrate`` runs the database checks before it migrates: on a new database the tables of
    apps do not exist yet, and the check must not stop the migration that creates them."""
    Module.objects.create(slug="ghost")

    with mock.patch.object(MigrationRecorder, "applied_migrations", return_value={}):
        assert check_module_slugs(app_configs=None, databases=["default"]) == []


def test_e001_runs_with_check_database_default():
    """Registered with the database tag: ``manage.py check --database default`` runs it."""
    Module.objects.create(slug="ghost")

    errors = checks.run_checks(tags=[checks.Tags.database], databases=["default"])

    assert "apps.E001" in [error.id for error in errors]


# --- Admin: the catalog read-only, Module with its validation (spec §5.5) -------------------------


@pytest.fixture
def superuser():
    return get_user_model().objects.create_superuser(
        email="root@example.com", password="x"
    )


@pytest.fixture
def staff_client(client, superuser):
    client.force_login(superuser)
    return client


@pytest.mark.parametrize("model", [App, AppDoc])
def test_the_catalog_has_no_add_change_or_delete_in_the_admin(superuser, model):
    """The Hub writes the catalog; the SaaS's admin only shows it."""
    app = make_app("inventory")
    row = app if model is App else make_doc(app)
    model_admin = admin.site._registry[model]
    request = RequestFactory().get("/admin/")
    request.user = superuser

    assert model_admin.has_view_permission(request, row)
    assert not model_admin.has_add_permission(request)
    assert not model_admin.has_change_permission(request, row)
    assert not model_admin.has_delete_permission(request, row)


def test_the_catalog_pages_show_the_rows_without_saving(staff_client):
    app = make_app("inventory")
    doc = make_doc(app)

    assert staff_client.get("/admin/apps/app/", HTTP_HOST=HOST).status_code == 200
    page = staff_client.get(f"/admin/apps/app/{app.pk}/change/", HTTP_HOST=HOST)
    assert page.status_code == 200
    assert 'name="_save"' not in page.content.decode()
    assert (
        staff_client.get(
            f"/admin/apps/appdoc/{doc.pk}/change/", HTTP_HOST=HOST
        ).status_code
        == 200
    )
    assert staff_client.get("/admin/apps/app/add/", HTTP_HOST=HOST).status_code == 403
    assert (
        staff_client.post(
            f"/admin/apps/app/{app.pk}/delete/", {"post": "yes"}, HTTP_HOST=HOST
        ).status_code
        == 403
    )
    assert App.objects.filter(pk=app.pk).exists()


def test_the_module_admin_refuses_an_app_that_is_not_in_the_catalog(staff_client):
    response = staff_client.post(
        "/admin/apps/module/add/", module_form("ghost"), HTTP_HOST=HOST
    )

    assert response.status_code == 200
    assert not Module.objects.exists()
    assert "There is no app “ghost” in the catalog" in response.content.decode()


def test_the_module_admin_adds_a_premium_app(staff_client):
    make_app("whatsapp_inbox", premium=True)

    response = staff_client.post(
        "/admin/apps/module/add/", module_form("whatsapp_inbox"), HTTP_HOST=HOST
    )

    assert response.status_code == 302
    module = Module.objects.get(slug="whatsapp_inbox")
    assert (module.price_monthly_cents, module.price_annual_cents) == (999, 9990)
    assert staff_client.get("/admin/apps/module/", HTTP_HOST=HOST).status_code == 200
    assert (
        staff_client.get(
            f"/admin/apps/module/{module.pk}/change/", HTTP_HOST=HOST
        ).status_code
        == 200
    )


def module_form(slug: str) -> dict[str, str]:
    return {
        "slug": slug,
        "tier": "basic",
        "price_monthly_cents": "999",
        "price_annual_cents": "9990",
        "stripe_product_id": "",
        "stripe_price_id_monthly": "",
        "stripe_price_id_annual": "",
        "is_active": "on",
    }
