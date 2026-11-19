from config.tests.production_settings import development, production


# WhatsApp's return page (whatsapp/signup_return.py): where Meta's window brings its one-time code back. Door 10 hands
# it to the Hub, which accepts it only from its SAAS_URL's origin, and door 11 exchanges the code with the same value.


def test_production_s_whatsapp_return_page_is_erplora_s_own_over_https():
    assert production("s.WHATSAPP_REDIRECT_URI") == "https://erplora.com/whatsapp/return"


def test_pre_s_whatsapp_return_page_follows_its_host():
    assert production("s.WHATSAPP_REDIRECT_URI", PUBLIC_HOST="pre.erplora.com") == "https://pre.erplora.com/whatsapp/return"


def test_development_s_whatsapp_return_page_is_the_local_saas():
    assert development("s.WHATSAPP_REDIRECT_URI") == "http://localhost:8001/whatsapp/return"


def test_the_whatsapp_return_page_may_be_given_by_the_environment():
    given = "http://localhost:8601/whatsapp/return"

    assert development("s.WHATSAPP_REDIRECT_URI", WHATSAPP_REDIRECT_URI=given) == given
