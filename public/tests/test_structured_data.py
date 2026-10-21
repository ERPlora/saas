"""JSON-LD builders of the public web (spec §8.2), ported from ERPlora/saas
``apps/public/structured_data.py`` and ``landing/tests/test_structured_data.py`` (origin/develop
c5ca8ca). The builders take data and read no model; the pages that call them (home, pricing,
industries, the app pages) test the blocks they render in their own batches.
"""

import json
from decimal import Decimal

from public.structured_data import (
    app_software_application,
    faq_page,
    industry_software_application,
    json_ld,
    organization,
    software_application,
)

BASE = "https://erplora.com"


class TestJsonLd:
    def test_it_is_valid_json(self):
        assert json.loads(json_ld({"name": "ERPlora", "price": "7.77"})) == {
            "name": "ERPlora",
            "price": "7.77",
        }

    def test_a_closing_script_tag_cannot_escape_the_block(self):
        """`</script>` in a value would close the tag and turn data into markup."""
        serialised = json_ld({"name": "</script><script>alert(1)</script>"})

        assert "</script>" not in serialised
        assert "<" not in serialised and ">" not in serialised
        assert json.loads(serialised)["name"] == "</script><script>alert(1)</script>"

    def test_ampersands_are_escaped_too(self):
        serialised = json_ld({"name": "Tom & Jerry"})

        assert "&" not in serialised
        assert json.loads(serialised)["name"] == "Tom & Jerry"

    def test_it_is_marked_safe_for_the_template(self):
        assert hasattr(json_ld({}), "__html__")

    def test_non_ascii_stays_readable(self):
        assert "Peluquería" in json_ld({"name": "Peluquería"})


class TestOrganization:
    def test_who_we_are(self):
        block = organization(BASE, f"{BASE}/static/img/logo.png")

        assert block["@context"] == "https://schema.org"
        assert block["@type"] == "Organization"
        assert block["name"] == "ERPlora"
        assert block["url"] == f"{BASE}/"
        assert block["logo"] == f"{BASE}/static/img/logo.png"
        assert block["contactPoint"]["url"] == f"{BASE}/contact/"


class TestSoftwareApplication:
    def test_it_names_the_product_category(self):
        """'ERP' and 'POS' are the words people type."""
        block = software_application(BASE, Decimal("7.77"), 12)

        assert block["@type"] == "SoftwareApplication"
        assert block["applicationCategory"] == "BusinessApplication"
        assert "ERP" in block["description"] and "POS" in block["description"]
        assert "12" in block["description"]

    def test_the_offer_carries_the_cheapest_price(self):
        offers = software_application(BASE, Decimal("7.77"), 12)["offers"]

        assert offers == {
            "@type": "Offer",
            "price": "7.77",
            "priceCurrency": "EUR",
            "url": f"{BASE}/pricing/",
            "availability": "https://schema.org/InStock",
        }

    def test_without_a_price_there_is_no_offer_rather_than_a_zero(self):
        """Advertising a price we do not charge is worse than advertising none."""
        assert "offers" not in software_application(BASE, None, 12)


class TestFaqPage:
    def test_it_is_built_from_the_visible_items(self):
        block = faq_page([{"question": "Is there a free plan?", "answer": "Yes."}])

        assert block["@type"] == "FAQPage"
        assert block["mainEntity"] == [
            {
                "@type": "Question",
                "name": "Is there a free plan?",
                "acceptedAnswer": {"@type": "Answer", "text": "Yes."},
            }
        ]

    def test_lazy_translations_become_text(self):
        from django.utils.translation import gettext_lazy

        block = faq_page(
            [{"question": gettext_lazy("Question"), "answer": gettext_lazy("Answer")}]
        )

        assert json.loads(json_ld(block))["mainEntity"][0]["name"] == "Question"


class TestIndustrySoftwareApplication:
    def test_it_describes_the_industry_page(self):
        block = industry_software_application(
            BASE,
            name="ERPlora for restaurants",
            url=f"{BASE}/industries/restaurant/",
            description="POS and kitchen for restaurants.",
            cheapest_price=Decimal("7.77"),
        )

        assert block["name"] == "ERPlora for restaurants"
        assert block["url"] == f"{BASE}/industries/restaurant/"
        assert block["offers"]["price"] == "7.77"
        assert "VeriFactu" not in json.dumps(block), (
            "the industry pages are pan-European"
        )

    def test_without_a_price_there_is_no_offer(self):
        block = industry_software_application(
            BASE, name="n", url="u", description="d", cheapest_price=None
        )

        assert "offers" not in block


class TestAppSoftwareApplication:
    """One block per app page (spec §8.2, decision 17): a free app is offered at 0; a premium one at
    the monthly price of the cheapest paid plan; no rating (there are no reviews)."""

    def _block(self, **overrides):
        values = {
            "name": "Inventory",
            "description": "Stock and warehouses.",
            "url": f"{BASE}/apps/inventory/",
            "premium": False,
            "cheapest_paid_price": Decimal("19.00"),
        }
        values.update(overrides)
        return app_software_application(BASE, **values)

    def test_a_free_app_is_offered_at_zero(self):
        block = self._block()

        assert block["@type"] == "SoftwareApplication"
        assert block["name"] == "Inventory"
        assert block["url"] == f"{BASE}/apps/inventory/"
        assert block["offers"]["price"] == "0"
        assert block["offers"]["priceCurrency"] == "EUR"

    def test_a_premium_app_is_offered_at_the_cheapest_paid_plan(self):
        offers = self._block(premium=True)["offers"]

        assert offers["price"] == "19.00"
        assert offers["url"] == f"{BASE}/pricing/"

    def test_a_premium_app_without_a_paid_plan_has_no_offer(self):
        assert "offers" not in self._block(premium=True, cheapest_paid_price=None)

    def test_there_is_no_rating(self):
        assert "aggregateRating" not in self._block()


class TestOperatingSystems:
    """PUBLIC-F14: the systems the product runs on are the ones it is distributed for (SAAS_PUBLIC-F75):
    the browser, the app for Windows and Linux (public/appdist.py) and Android through Google Play.
    No macOS build and no iOS app are published."""

    BLOCKS = {
        "home": lambda: software_application(BASE, Decimal("0"), 3),
        "industry": lambda: industry_software_application(
            BASE, name="n", url="u", description="d", cheapest_price=None
        ),
        "app": lambda: app_software_application(
            BASE, name="n", description="d", url="u", premium=False, cheapest_paid_price=None
        ),
    }

    def test_every_block_names_the_systems_we_distribute(self):
        for name, build in self.BLOCKS.items():
            assert build()["operatingSystem"] == "Web, Windows, Linux, Android", name

    def test_the_systems_are_the_platforms_the_app_page_serves(self):
        from public.appdist import _APP_PLATFORM_FILES

        systems = software_application(BASE, None, 0)["operatingSystem"].lower()

        assert all(platform in systems for platform in _APP_PLATFORM_FILES)
        assert "macos" not in systems and "ios" not in systems.split(", ")
