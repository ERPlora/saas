"""Models of hubs: ``Plan`` (PLAN-SAAS §1, without infrastructure) and the taxonomy (PLAN §21.4).

Ported from ERPlora/saas (origin/develop): the pure-model halves of
``public/pricing/tests/test_internal_plans_are_never_public.py``,
``hubs/main/tests/test_internal_plan_gate_after_alta.py`` (``TestOfferedTo``),
``hubs/subscriptions/tests/test_payment_test_plan.py`` and ``test_plan_trial_label.py``. The
pages, forms and Stripe halves stay with the lots that port those doors.
"""

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.utils import translation

from apps.tests.factories import make_app
from hubs.models import Plan

INTERNAL = "payment-test"


def _plan(slug="starter", trial_days=0, **extra):
    return Plan(slug=slug, name_en=slug.title(), price_monthly=Decimal("29.99"), trial_period_days=trial_days, **extra)


def _create(slug, **extra):
    return Plan.objects.create(**{"name_en": slug.title(), "price_monthly": Decimal("5"), "slug": slug, **extra})


@pytest.fixture
def plans(db):
    """The catalogue the migrations leave (``hubs/0013``)."""


@pytest.fixture
def customer(django_user_model):
    return django_user_model.objects.create_user(email="client@example.com", password="x")


@pytest.fixture
def staff(django_user_model):
    return django_user_model.objects.create_user(email="staff@example.com", password="x", is_staff=True)


# --- Identity ------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_plan_has_a_uuid7_primary_key():
    plan = _create("bakery-special")

    assert isinstance(plan.pk, uuid.UUID)
    assert plan.pk.version == 7


def test_a_plan_reads_as_its_name_and_monthly_price():
    assert str(_plan()) == "Starter - EUR 29.99/month"


def test_plans_are_listed_by_display_order_then_price():
    assert Plan._meta.ordering == ["display_order", "price_monthly"]


# --- Public plans (saas#1950) and who may buy which (saas#1052, saas#2388) -----------------------


@pytest.mark.django_db
def test_public_queryset_keeps_active_customer_plans_only(plans):
    _create("internal-sentinel", internal_only=True, display_order=-100)
    _create("retired-sentinel", is_active=False)

    slugs = set(Plan.objects.public().values_list("slug", flat=True))

    assert "starter" in slugs
    assert {INTERNAL, "internal-sentinel", "retired-sentinel"}.isdisjoint(slugs)


class TestOfferedTo:
    """``Plan.objects.offered_to(user)``: the one rule every logged-in door lists plans through."""

    def _slugs(self, user):
        return set(Plan.objects.offered_to(user).values_list("slug", flat=True))

    def test_nobody_and_anonymous_get_only_public_plans(self, plans):
        assert INTERNAL not in self._slugs(None)
        assert INTERNAL not in self._slugs(AnonymousUser())

    def test_staff_gets_every_active_plan(self, plans, staff):
        assert self._slugs(staff) == set(Plan.objects.filter(is_active=True).values_list("slug", flat=True))

    def test_a_customer_gets_exactly_the_public_plans(self, plans, customer):
        assert self._slugs(customer) == set(Plan.objects.public().values_list("slug", flat=True))

    def test_an_inactive_plan_is_offered_to_nobody(self, plans, staff):
        Plan.objects.filter(slug=INTERNAL).update(is_active=False)

        assert INTERNAL not in self._slugs(staff)


class TestOnlyStaffCanBuyTheInternalPlan:
    """Purchasable, but not by anyone: it is a whole hub for 1.21 €."""

    def test_internal_defaults_to_false_so_real_plans_are_unaffected(self):
        assert Plan._meta.get_field("internal_only").default is False

    def test_is_available_to_rejects_a_regular_user(self, plans, customer):
        assert Plan.objects.get(slug=INTERNAL).is_available_to(customer) is False

    def test_is_available_to_rejects_an_anonymous_visitor(self, plans):
        assert Plan.objects.get(slug=INTERNAL).is_available_to(AnonymousUser()) is False
        assert Plan.objects.get(slug=INTERNAL).is_available_to(None) is False

    def test_is_available_to_accepts_staff(self, plans, staff):
        assert Plan.objects.get(slug=INTERNAL).is_available_to(staff) is True

    def test_a_normal_plan_is_available_to_everyone(self, plans, customer):
        assert Plan.objects.get(slug="starter").is_available_to(customer) is True


# --- The trial a visitor gets (saas#2414, saas#2424) ---------------------------------------------


class TestSignupTrialDays:
    """``Plan.objects.signup_trial_days()``: every public page that states the trial reads it here."""

    def test_the_catalogue_offers_no_trial(self, plans):
        """Ioan, 2026-10-15: the Free plan is the way in; no plan on sale carries a trial."""
        assert Plan.objects.signup_trial_days() == {"trial_days_min": None, "trial_days_max": None}

    def test_only_public_plans_bought_at_sign_up_count(self, signup_trial):
        """An upgrade grants no trial (#809), an internal plan is no offer, a retired one neither."""
        _create("long-upgrade", trial_period_days=90, upgrade_only=True)
        _create("long-internal", trial_period_days=60, internal_only=True)
        _create("long-retired", trial_period_days=45, is_active=False)
        _create("short", trial_period_days=7)

        assert Plan.objects.signup_trial_days() == {"trial_days_min": 7, "trial_days_max": 15}

    def test_none_when_no_plan_on_sale_has_a_trial(self, no_plans):
        _create("free", trial_period_days=0)

        assert Plan.objects.signup_trial_days() == {"trial_days_min": None, "trial_days_max": None}


class TestTrialLabel:
    def test_states_the_plan_trial_in_english(self):
        with translation.override("en"):
            assert _plan(trial_days=21).trial_label == "21-day free trial"

    def test_states_the_plan_trial_in_spanish(self):
        with translation.override("es"):
            assert _plan(trial_days=21).trial_label == "21 días de prueba gratis"

    def test_a_single_day_is_singular_in_spanish(self):
        with translation.override("es"):
            assert _plan(trial_days=1).trial_label == "1 día de prueba gratis"

    def test_no_trial_no_label(self):
        assert _plan(trial_days=0).trial_label == ""
        assert _plan(trial_days=0).has_trial() is False


# --- The commercial ladder, translated (ADR-0474, ADR-0426) ---------------------------------------


@pytest.mark.parametrize(
    ("included", "support", "english", "spanish"),
    [
        ("free", "community", ("Free", "Community forum"), ("Gratis", "Foro de la comunidad")),
        ("basic", "email", ("Basic", "Email"), ("Basic", "Correo electrónico")),
        ("pro", "priority_email", ("Pro", "Priority email"), ("Pro", "Correo electrónico prioritario")),
        ("enterprise", "contract", ("Enterprise", "Agreed in contract"), ("Enterprise", "Acordado en contrato")),
    ],
)
def test_the_level_labels_are_read_in_the_active_language(included, support, english, spanish):
    plan = _plan(included_level=included, support_level=support)

    with translation.override("en"):
        assert (plan.included_level_label, plan.support_level_label) == english
    with translation.override("es"):
        assert (plan.included_level_label, plan.support_level_label) == spanish


@pytest.mark.parametrize(
    ("max_devices", "connections", "english", "spanish"),
    [
        (1, 1, "Basic, for one device", "Básica, para un dispositivo"),
        (0, 3, "Full, for several devices", "Completa, para varios dispositivos"),
        (0, 6, "Double", "El doble"),
        (0, 9, "Triple", "El triple"),
    ],
)
def test_the_resources_label_reads_the_database_ladder_in_plain_words(max_devices, connections, english, spanish):
    """Ioan, 2026-10-15: a buyer reads how much database throughput a plan has relative to the plan below, never a
    connection count. Free is sized for one device; a paid plan has the full tier; Standard twice it."""
    plan = _plan(max_devices=max_devices, max_db_connections=connections)

    with translation.override("en"):
        assert plan.resources_label == english
    with translation.override("es"):
        assert plan.resources_label == spanish


# --- One column per language ----------------------------------------------------------------------


class TestPlanCopyInALanguage:
    """No modeltranslation: ``<field>_en`` is the source, ``<field>_es`` its translation."""

    def _plan(self):
        return _plan(
            name_es="Inicial",
            description_en="Your business",
            description_es="",
            features_en=["Unlimited users"],
            features_es=["Usuarios ilimitados"],
        )

    def test_spanish_reads_the_spanish_column(self):
        plan = self._plan()

        assert plan.translated("name", "es") == "Inicial"
        assert plan.translated("features", "es") == ["Usuarios ilimitados"]

    def test_a_blank_translation_falls_back_to_english(self):
        assert self._plan().translated("description", "es") == "Your business"

    def test_a_regional_or_unknown_language_reads_the_closest_column(self):
        plan = self._plan()

        assert plan.translated("name", "es-ES") == "Inicial"
        assert plan.translated("name", "fr") == "Starter"

    def test_without_a_language_it_reads_the_active_one(self):
        plan = self._plan()

        with translation.override("es"):
            assert plan.translated("name") == "Inicial"
        with translation.override("en"):
            assert plan.translated("name") == "Starter"


# --- The taxonomy: sectors and business types (PLAN §21.4) ----------------------------------------


@pytest.fixture
def hospitality(db):
    from hubs.models import Sector

    return Sector.objects.create(
        code="hospitality",
        name_en="Hospitality & Food",
        name_es="Hostelería y Alimentación",
        description_en="Restaurants, bars",
        description_es="",
    )


@pytest.mark.django_db
def test_sectors_and_business_types_have_uuid7_primary_keys(hospitality):
    from hubs.models import BusinessType

    bar = BusinessType.objects.create(code="bar", name_en="Bar", name_es="Bar", sector=hospitality)

    assert (hospitality.pk.version, bar.pk.version) == (7, 7)


def test_a_sector_and_a_business_type_read_as_their_english_name():
    from hubs.models import BusinessType, Sector

    assert str(Sector(code="retail", name_en="Retail & Commerce")) == "Retail & Commerce"
    assert str(BusinessType(code="bar", name_en="")) == "bar"


class TestTaxonomyInALanguage:
    """``name(language)`` and ``description(language)``: the API serves the row in the request's."""

    def test_spanish_reads_the_spanish_columns(self, hospitality):
        assert hospitality.name("es") == "Hostelería y Alimentación"

    def test_a_blank_spanish_column_falls_back_to_english(self, hospitality):
        assert hospitality.description("es") == "Restaurants, bars"

    def test_english_and_the_active_language(self, hospitality):
        assert hospitality.name("en") == "Hospitality & Food"
        with translation.override("es"):
            assert hospitality.name() == "Hostelería y Alimentación"


class TestVertical:
    """``BusinessType.vertical``: the template a new hub of that type is cloned from (PLAN §15.2).

    Blank is «no vertical» (the hub starts from ``hub_template``, only ``base``). The Hub names the
    template database after it (``hub_template_<vertical>``), so it is an identifier.
    """

    def test_blank_by_default(self):
        from hubs.models import BusinessType

        assert BusinessType(code="bar", name_en="Bar").vertical == ""

    @pytest.mark.django_db
    def test_a_vertical_is_lowercase_letters_digits_and_underscores(self):
        from hubs.models import BusinessType

        make_app("appointment", verticals=["hair_salon"])
        BusinessType(code="hair_salon", name_en="Hair Salon", vertical="hair_salon").full_clean()
        for wrong in ("Hair Salon", "hair-salon", "_salon", "salón"):
            with pytest.raises(ValidationError) as refused:
                BusinessType(code="hair_salon", name_en="Hair Salon", vertical=wrong).full_clean()
            assert "vertical" in refused.value.message_dict, wrong

    @pytest.mark.django_db
    def test_a_vertical_some_app_of_the_catalog_declares_is_accepted(self):
        """``apps.queries.known_verticals()``: the verticals the Hub registered with its apps (spec §5.4)."""
        from hubs.models import BusinessType

        make_app("appointment", verticals=["hair_salon"])
        make_app("table", verticals=["restaurant"])

        BusinessType(code="barber_shop", name_en="Barber Shop", vertical="hair_salon").full_clean()
        BusinessType(code="tapas_bar", name_en="Tapas Bar", vertical="restaurant").full_clean()

    @pytest.mark.django_db
    def test_a_vertical_no_app_declares_is_refused(self):
        """A typo would name a template the Hub does not have: the sign-up would fail later, in the Hub."""
        from hubs.models import BusinessType

        make_app("appointment", verticals=["hair_salon"])

        with pytest.raises(ValidationError) as refused:
            BusinessType(code="bakery", name_en="Bakery", vertical="bakery").full_clean()

        assert [error.code for error in refused.value.error_dict["vertical"]] == ["unknown_vertical"]

    @pytest.mark.django_db
    def test_a_retired_app_still_vouches_for_its_vertical(self):
        """Its row stays in the catalog (``listed = False``), and so does the template it built."""
        from hubs.models import BusinessType

        make_app("old_agenda", verticals=["hair_salon"], listed=False)

        BusinessType(code="hair_salon", name_en="Hair Salon", vertical="hair_salon").full_clean()

    @pytest.mark.django_db
    def test_no_vertical_needs_no_catalog(self):
        from hubs.models import BusinessType

        BusinessType(code="bar", name_en="Bar", vertical="").full_clean()
