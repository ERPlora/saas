"""What a session's user agent says about where it runs (Account → Security → Active sessions): the device,
the browser and its version, or the ERPlora app (ported from the old hub's ``default_device_name``,
``crates/server/src/devices.rs``: proper nouns and codes, nothing to translate in the database)."""

import pytest

from accounts.devices import describe

CHROME_MAC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.6723.92 Safari/537.36"
)
EDGE_WINDOWS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36 Edg/130.0.2849.68"
)
SAFARI_IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/18.0 Mobile/15E148 Safari/604.1"
)
CHROME_IPAD = (
    "Mozilla/5.0 (iPad; CPU OS 17_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "CriOS/129.0.6668.69 Mobile/15E148 Safari/604.1"
)
FIREFOX_LINUX = "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0"
OPERA_WINDOWS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/129.0.0.0 Safari/537.36 OPR/114.0.0.0"
)
CHROMEBOOK = (
    "Mozilla/5.0 (X11; CrOS x86_64 14541.0.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
APP_ANDROID = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
    "Chrome/130.0.6723.86 Mobile Safari/537.36 ERPloraApp/4.0.2"
)
APP_WINDOWS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0 ERPloraApp/4.0"
)


@pytest.mark.parametrize(
    "user_agent, expected",
    [
        (CHROME_MAC, ("mac", "Chrome", "130", None)),
        (EDGE_WINDOWS, ("windows", "Edge", "130", None)),
        (SAFARI_IPHONE, ("iphone", "Safari", "18", None)),
        (CHROME_IPAD, ("ipad", "Chrome", "129", None)),
        (FIREFOX_LINUX, ("linux", "Firefox", "131", None)),
        (OPERA_WINDOWS, ("windows", "Opera", "114", None)),
        (CHROMEBOOK, ("chromeos", "Chrome", "130", None)),
        (APP_ANDROID, ("android", "", "", "4.0.2")),
        (APP_WINDOWS, ("windows", "", "", "4.0")),
    ],
)
def test_the_device_the_browser_and_the_app(user_agent, expected):
    device = describe(user_agent)

    assert (device.platform, device.browser, device.browser_version, device.app_version) == expected


def test_an_unreadable_agent_says_nothing_rather_than_inventing():
    device = describe("curl/8.4.0")

    assert (device.platform, device.browser, device.browser_version, device.app_version) == ("", "", "", None)


def test_half_an_answer_is_kept():
    assert describe("Mozilla/5.0 (Windows NT 10.0)").platform == "windows"
    assert describe("Firefox/115.0").browser == "Firefox"
