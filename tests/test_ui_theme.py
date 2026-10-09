"""Phase 5: dark theme, responsive layout, loading states and clear errors."""
import pytest

pytestmark = pytest.mark.browser
ROUTES = ["tts", "library", "voices", "clone", "blend", "changer", "dialogue", "batch", "dictionary",
          "history", "api", "usage", "settings"]


@pytest.fixture()
def browser():
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def no_side_scroll(pg):
    return pg.evaluate("document.documentElement.scrollWidth <= innerWidth && document.querySelector('main').scrollWidth <= document.querySelector('main').clientWidth")


@pytest.mark.parametrize("size", [(390, 844), (768, 1024), (1440, 900)])
def test_every_view_fits_without_sideways_scroll(browser, live_server, size):
    pg = browser.new_page(viewport={"width": size[0], "height": size[1]})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    for r in ROUTES:
        pg.goto(f"{live_server}/#{r}")
        pg.wait_for_selector("main h1")
        pg.wait_for_timeout(150)
        assert no_side_scroll(pg), (r, size)
        active = pg.query_selector("#nav a.active")
        assert active and active.is_visible()
        box = active.bounding_box()
        assert 0 <= box["x"] and box["x"] + box["width"] <= size[0] + 1, (r, box)   # active tab scrolled into view
    assert not errors, errors


def test_dark_theme_and_page_basics(browser, live_server):
    pg = browser.new_page()
    pg.goto(live_server + "/#clone")
    bg = pg.evaluate("getComputedStyle(document.body).backgroundColor")
    r, g, b = (int(x) for x in bg[bg.index("(") + 1:-1].split(",")[:3])
    assert max(r, g, b) < 40                                     # dark background
    assert pg.evaluate("getComputedStyle(document.documentElement).colorScheme") == "dark"
    assert pg.get_attribute("#nav a.active", "aria-current") == "page"
    assert pg.query_selector("link[rel=icon]")                   # no favicon 404 round-trip


def test_server_error_detail_is_shown(browser, live_server):
    pg = browser.new_page()
    pg.route("**/api/blend/sources", lambda route: route.fulfill(
        status=500, content_type="application/json", body='{"detail": "Voice store is unavailable"}'))
    pg.goto(live_server + "/#blend")
    pg.wait_for_selector("#blend-msg.error")
    assert "Voice store is unavailable" in pg.inner_text("#blend-msg")


def test_server_unreachable_is_explained(browser, live_server, tmp_path):
    import numpy as np
    import soundfile as sf

    f = tmp_path / "a.wav"
    sf.write(f, np.zeros(8000, np.float32), 8000)
    pg = browser.new_page()
    pg.goto(live_server + "/#clone")
    pg.route("**/api/clone/drafts**", lambda route: route.abort())
    pg.set_input_files("#clone-input", str(f))
    pg.wait_for_selector("#clone-msg.error")
    assert "Cannot reach the server" in pg.inner_text("#clone-msg")


def test_unexpected_error_shows_toast(browser, live_server):
    pg = browser.new_page()
    pg.goto(live_server + "/#tts")
    pg.wait_for_selector("main h1")
    pg.evaluate("setTimeout(() => Promise.reject(new Error('disk full')), 0)")
    pg.wait_for_selector("#toast:not([hidden])")
    assert "disk full" in pg.inner_text("#toast")


def test_loading_state_while_waiting(browser, live_server):
    """Slow server: the blend pickers show a loading label until voices arrive."""
    pg = browser.new_page()
    held = []
    pg.route("**/api/blend/sources", lambda route: held.append(route))   # hold the request until released
    pg.goto(live_server + "/#blend")
    pg.wait_for_selector("#blend-a")
    while not held:
        pg.wait_for_timeout(50)
    assert "Loading" in pg.inner_text("#blend-a")
    held[0].continue_()
    pg.wait_for_selector("#blend-a option[value='xtts-daisy-studious']", state="attached")


def test_tts_page_shows_server_error(browser, live_server):
    page = browser.new_page()
    page.goto(live_server + "/#tts")
    page.wait_for_selector("#tts-voice option[value='piper-en-us-lessac-medium']", state="attached")
    page.select_option("#tts-voice", "piper-en-us-lessac-medium")
    page.fill("#tts-text", "Hola.")
    page.select_option("#tts-lang", "es")
    page.route("**/api/tts", lambda r: r.fulfill(status=400, json={"detail": "Engine 'x' does not support language 'es'"}))
    page.click("#tts-generate")
    page.wait_for_selector("#tts-msg.error")
    assert "does not support language" in page.inner_text("#tts-msg")
    assert not page.is_disabled("#tts-generate")


def test_sidebar_collapse_button(browser, live_server):
    pg = browser.new_page(viewport={"width": 1440, "height": 900})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(live_server + "/#library")
    pg.wait_for_selector("#nav a.active")
    wide = pg.evaluate("document.querySelector('#sidebar').getBoundingClientRect().width")
    assert pg.inner_text("#nav a.active") == "Voice Library" and pg.query_selector("#nav a.active svg.nav-icon")
    assert pg.get_attribute("#nav-toggle", "aria-expanded") == "true"
    pg.click("#nav-toggle")                                          # minimize: icons only
    pg.wait_for_timeout(300)
    assert pg.evaluate("document.body.classList.contains('nav-collapsed')")
    assert pg.evaluate("document.querySelector('#sidebar').getBoundingClientRect().width") < wide / 2
    assert pg.evaluate("getComputedStyle(document.querySelector('#nav a.active')).fontSize") == "0px"   # label hidden
    assert pg.is_visible("#nav a.active svg")
    assert pg.get_attribute("#nav a[data-route=history]", "title") == "History"     # name shown on hover
    assert pg.get_attribute("#nav-toggle", "aria-expanded") == "false"
    assert pg.get_attribute("#nav-toggle", "aria-label") == "Expand menu"
    pg.reload()                                                      # remembered in this browser
    pg.wait_for_selector("#nav a.active")
    assert pg.evaluate("document.body.classList.contains('nav-collapsed')")
    pg.select_option("#ui-lang", "es") if pg.is_visible("#ui-lang") else pg.evaluate("setLang('es')")
    assert pg.get_attribute("#nav-toggle", "aria-label") == "Expandir menú"
    pg.click("#nav-toggle")                                          # maximize again
    pg.wait_for_timeout(300)
    assert pg.evaluate("getComputedStyle(document.querySelector('#nav a.active')).fontSize") != "0px"
    assert pg.get_attribute("#nav-toggle", "aria-label") == "Contraer menú"
    pg.evaluate("setLang('en')")
    pg.set_viewport_size({"width": 390, "height": 844})               # phone: no toggle, labels shown
    assert not pg.is_visible("#nav-toggle")
    assert pg.evaluate("getComputedStyle(document.querySelector('#nav a.active')).fontSize") != "0px"
    assert not errors, errors


@pytest.mark.parametrize("width", [1440, 2560])
def test_page_scrollbar_is_at_window_edge(browser, live_server, width):
    pg = browser.new_page(viewport={"width": width, "height": 700})
    for r in ("library", "tts"):
        pg.goto(f"{live_server}/#{r}")
        pg.wait_for_selector("main h1")
        right = pg.evaluate("document.querySelector('main').getBoundingClientRect().right")
        assert abs(right - width) <= 1, (r, right)                     # scroll area reaches the right edge
        h1 = pg.query_selector("main h1").bounding_box()
        assert h1["x"] + h1["width"] <= 236 + 1520, (r, h1)             # content keeps its max width
