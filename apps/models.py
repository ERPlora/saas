"""Models of apps: the catalog the Hub registers and what the SaaS sells (round 16, PLAN §21).

- ``App`` and ``AppDoc`` concrete ``live.shared_catalog`` in the ``shared`` schema of the ``saas``
  database (spec §3.2). The SaaS owns the tables and their migrations, the Hub writes them with
  each release (its mirror is ``managed = False``) and the SaaS only reads them: through
  ``apps/queries.py``, its read-only admin and its checks (``apps/tests/test_lint.py``).
- ``Module`` is only commercial (spec decision 7, PLAN-SAAS §2.6): one row per paid app, written by
  hand in the admin. Name, texts, icon and documentation come from ``App``. ``slug`` points at
  ``App.id`` without a database FK (nothing crosses the ``shared`` schema): ``clean()`` and the
  database check ``apps.E001`` keep it honest (spec §5.4).
"""

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel
from live.shared_catalog import APP_DOC_TABLE, APP_TABLE, AbstractApp, AbstractAppDoc

#: The label of an app = its folder in the Hub = ``shared.app.id`` (round 15, PLAN §20.2).
APP_ID_RE = r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$"


class App(AbstractApp):
    """A module some release of the Hub knew; ``listed = False`` keeps it out of the store."""

    class Meta:
        db_table = APP_TABLE
        ordering = ["id"]
        verbose_name = _("app")
        verbose_name_plural = _("apps")

    def __str__(self) -> str:
        return self.id


class AppDoc(AbstractAppDoc):
    """The user documentation of an app in one language (the WORKBOOK's user part)."""

    class Meta:
        db_table = APP_DOC_TABLE
        constraints = [
            models.UniqueConstraint(
                fields=["app", "lang"], name="shared_app_doc_app_lang_unique"
            )
        ]
        verbose_name = _("app documentation")
        verbose_name_plural = _("app documentation")

    def __str__(self) -> str:
        return f"{self.app_id} ({self.lang})"


class Module(UUIDModel):
    """What the SaaS sells of a paid app (``premium = True`` in the Hub): its tier, prices and Stripe.

    A free app never has a row: it is always entitled (PLAN-SAAS §2.6). Prices are net (VAT
    excluded) and in euro cents, the integer Stripe charges, so no amount is ever rounded here.
    """

    class Tier(models.TextChoices):
        """The lowest level of a hub plan that includes the module (ADR-0474; the same names as
        ``Plan.included_level``): ``basic`` = every paid plan."""

        FREE = "free", _("Free")
        BASIC = "basic", _("Basic")
        PRO = "pro", _("Pro")
        ENTERPRISE = "enterprise", _("Enterprise")

    slug = models.CharField(
        _("app"),
        max_length=63,
        unique=True,
        validators=[
            RegexValidator(
                APP_ID_RE,
                _("Enter the label of an app of the Hub (inventory, whatsapp_inbox…)."),
            )
        ],
        help_text=_("The label of the paid app in the Hub, as the catalog lists it."),
    )
    tier = models.CharField(
        _("tier"), max_length=16, choices=Tier.choices, default=Tier.BASIC
    )
    price_monthly_cents = models.PositiveIntegerField(
        _("monthly price (cents)"),
        default=0,
        help_text=_("Net monthly price in euro cents, VAT excluded."),
    )
    price_annual_cents = models.PositiveIntegerField(
        _("annual price (cents)"),
        default=0,
        help_text=_(
            "Net annual price in euro cents, VAT excluded (0 = no annual option)."
        ),
    )
    stripe_product_id = models.CharField(
        _("Stripe product"), max_length=255, blank=True
    )
    stripe_price_id_monthly = models.CharField(
        _("Stripe monthly price"), max_length=255, blank=True
    )
    stripe_price_id_annual = models.CharField(
        _("Stripe annual price"), max_length=255, blank=True
    )
    is_active = models.BooleanField(
        _("active"), default=True, help_text=_("On sale for new purchases.")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["slug"]
        verbose_name = _("module")
        verbose_name_plural = _("modules")

    def __str__(self) -> str:
        return self.slug

    def clean(self) -> None:
        """The slug is an app of the catalog, and a paid one; a retired app (``listed = False``)
        still exists, so its row is valid (spec §5.4)."""
        super().clean()
        if not self.slug:
            return
        premium = (
            App.objects.filter(pk=self.slug).values_list("premium", flat=True).first()
        )
        if premium is None:
            raise ValidationError(
                {
                    "slug": ValidationError(
                        _(
                            "There is no app “%(slug)s” in the catalog: the Hub registers its apps when it starts."
                        ),
                        code="unknown_app",
                        params={"slug": self.slug},
                    )
                }
            )
        if not premium:
            raise ValidationError(
                {
                    "slug": ValidationError(
                        _(
                            "The app “%(slug)s” is free: only a paid (premium) app is sold as a module."
                        ),
                        code="free_app",
                        params={"slug": self.slug},
                    )
                }
            )
