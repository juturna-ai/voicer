"""Phase 5: interface language switch (English / Spanish)."""
import json
import re
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent.parent / "voicer" / "web"
ROUTES = ["tts", "library", "voices", "clone", "blend", "changer", "dialogue", "batch", "dictionary",
          "history", "api", "usage", "settings"]
# Strings that are the same in both languages, or are not interface text.
SAME = {"English", "Español", "XTTS-v2", "F5-TTS"}

VISIBLE_TEXT = """() => {
  const out = [];
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (w.nextNode()) {
    const n = w.currentNode, el = n.parentElement;
    if (!el || el.closest('script,style,[hidden],[lang=en]') || !n.textContent.trim()) continue;   // lang=en: API reference
    if (el.closest('select') && !el.closest('option')) continue;
    out.push(n.textContent.trim());
  }
  for (const el of document.querySelectorAll('[placeholder],[aria-label],[title]'))
    for (const a of ['placeholder', 'aria-label', 'title']) if (el.getAttribute(a)) out.push(el.getAttribute(a).trim());
  for (const og of document.querySelectorAll('optgroup')) out.push(og.label);
  return out;
}"""


def es_dict():
    src = (WEB / "i18n.js").read_text()
    js = src + ";console.log(JSON.stringify(I18N.es))"
    out = subprocess.run(["node", "-e", "global.localStorage={getItem:()=>null};global.navigator={language:'en'};" + js],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_every_key_has_a_spanish_translation():
    es = es_dict()
    app = (WEB / "app.js").read_text()
    keys = set(re.findall(r'\bt\(\s*"((?:[^"\\]|\\.)*)"', app))
    keys |= set(re.findall(r'field\("([^"]+)"', app))
    keys |= set(re.findall(r'\["\w+", "([^"]+)"\]', app[: app.index("];")]))      # NAV labels
    issues = app[app.index("const ISSUE_TEXT"): app.index("const issueText")]
    keys |= set(re.findall(r': "([^"]+)"', issues))
    keys -= SAME
    missing = sorted(k for k in keys if k not in es)
    assert not missing, missing
    # Placeholders must survive translation.
    for k, v in es.items():
        assert set(re.findall(r"\{\w+\}", k)) == set(re.findall(r"\{\w+\}", v)), k


@pytest.mark.browser
def test_switch_to_spanish_on_every_route_and_remember(page, live_server):
    es = es_dict()
    english = {k for k, v in es.items() if k != v and len(k) > 2 and "{" not in k}
    page.goto(f"{live_server}/#tts")
    page.wait_for_selector("#ui-lang")
    assert page.input_value("#ui-lang") == "en"
    assert page.inner_text("#nav a[data-route=library]") == "Voice Library"
    page.select_option("#ui-lang", "es")
    assert page.inner_text("#nav a[data-route=library]") == es["Voice Library"]
    assert page.evaluate("document.documentElement.lang") == "es"
    for r in ROUTES:
        page.goto(f"{live_server}/#{r}")
        page.wait_for_selector("main h1")
        page.wait_for_timeout(300)                      # async content (status, blend voices)
        left = [s for s in page.evaluate(VISIBLE_TEXT) if s in english]
        assert not left, (r, left)
    # Survives a reload, and the quality panel translates warning codes.
    page.reload()
    page.wait_for_selector("main h1")
    assert page.input_value("#ui-lang") == "es"
    assert page.inner_text("main h1") == es["Settings"]
    q = page.evaluate("issueText({code: 'short', seconds: 5})")
    assert q.startswith("Solo 5 s"), q
    # Back to English.
    page.select_option("#ui-lang", "en")
    assert page.inner_text("main h1") == "Settings"
    page.reload()
    page.wait_for_selector("main h1")
    assert page.input_value("#ui-lang") == "en"
