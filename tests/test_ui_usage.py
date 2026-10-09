"""Phase 10: Usage page — totals and tables per voice, app/agent, API key/device and connection."""
import httpx
import pytest

pytestmark = pytest.mark.browser

EN = "piper-en-us-lessac-medium"


def test_usage_page_shows_totals_and_tables(page):
    r = httpx.post(f"{page.base}/api/speak", json={"text": "Usage page check.", "voice": EN},
                   headers={"X-Voicer-Agent": "UI usage test bot"}, timeout=120)
    assert r.status_code == 200, r.text
    s = httpx.get(f"{page.base}/api/usage", params={"days": 30}).json()

    page.goto(page.base + "/#usage")
    page.wait_for_selector("#use-totals")
    nums = page.eval_on_selector_all("#use-totals .usage-num", "n => n.map(x => x.textContent)")
    assert len(nums) == 3 and int(nums[0].replace(",", "")) == s["totals"]["requests"] >= 1
    agents = page.eval_on_selector_all("#use-agent tbody tr", "rs => rs.map(r => [...r.cells].map(c => c.textContent))")
    bot = [a for a in agents if a[0] == "UI usage test bot"]
    assert bot and bot[0][1] == "1" and bot[0][2] == "17"
    assert any(v[0] == "Lessac (Piper)" or EN in v[0] for v in
               page.eval_on_selector_all("#use-voice tbody tr", "rs => rs.map(r => [...r.cells].map(c => c.textContent))"))
    assert "This PC" in page.inner_text("#use-key") and "REST API" in page.inner_text("#use-channel")
    assert page.input_value("#use-days") == "30"

    page.select_option("#use-days", "0")                       # all time: remembered on reload
    page.wait_for_function("document.querySelector('#use-totals')")
    page.reload()
    page.wait_for_selector("#use-totals")
    assert page.input_value("#use-days") == "0"
    page.select_option("#use-days", "30")


def test_usage_page_empty_period_and_phone_width(page):
    page.set_viewport_size({"width": 390, "height": 800})
    page.route("**/api/usage?*", lambda route: route.fulfill(json={
        "days": 1, "since": None, "totals": {"requests": 0, "characters": 0, "seconds": 0, "minutes": 0},
        "by_voice": [], "by_agent": [], "by_key": [], "by_channel": [], "by_day": []}))
    page.goto(page.base + "/#usage")
    page.wait_for_selector("#use-totals")
    assert page.inner_text("#use-agent").count("Nothing in this period.") == 1
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")   # no sideways scroll
