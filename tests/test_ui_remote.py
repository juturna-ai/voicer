"""Phase 10: API page card "Remote access (Tailscale)": status and the steps to share the server."""
import pytest

pytestmark = pytest.mark.browser

TS = "voicer-pc.tail1234.ts.net"


def test_remote_card_not_installed_then_sharing(page):
    page.goto(page.base + "/#api")
    page.wait_for_selector("#remote-status")
    assert "Tailscale is not installed." in page.inner_text("#remote-status")     # this test machine
    assert "tailscale serve --bg http://127.0.0.1:" in page.inner_text("#remote-serve")
    assert "API key is off" in page.inner_text("#remote-box")

    page.route("**/api/remote-access", lambda r: r.fulfill(json={
        "installed": True, "where": "windows", "running": True, "dns_name": TS, "ips": ["100.101.102.103"],
        "serving": True, "funnel": True, "url": f"https://{TS}", "api_key_on": False, "port": 8765, "warnings": []}))
    page.reload()
    page.wait_for_selector("#remote-status")
    assert f"Shared on your tailnet: https://{TS}" in page.inner_text("#remote-status")
    assert f"curl https://{TS}/api/voices" in page.inner_text("#remote-test")
    warnings = page.eval_on_selector_all(".remote-warning", "w => w.map(x => x.textContent)")
    assert len(warnings) == 2 and "Funnel" in warnings[0]
    page.click("#api-key-create")                                  # making a key clears the key warning
    page.wait_for_selector("#api-key-value")
    assert page.eval_on_selector_all(".remote-warning", "w => w.length") == 1
    page.once("dialog", lambda d: d.accept())
    page.click("#api-key-off")
    page.wait_for_selector("#api-key-create")


def test_remote_card_hidden_from_other_devices(page):
    page.route("**/api/remote-access", lambda r: r.fulfill(status=403, json={"detail": "Shown only on the PC that runs Voice Studio"}))
    page.goto(page.base + "/#api")
    page.wait_for_selector("#remote-status")
    assert "shown only on the PC" in page.inner_text("#remote-status")
    page.errors[:] = [e for e in page.errors if "status of 403" not in e]
