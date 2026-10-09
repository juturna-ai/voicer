"""Spell out numbers, dates, money, times, abbreviations and URLs so TTS reads them right (es/en)."""
from __future__ import annotations

import re

from num2words import num2words

MONTHS = {
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
           "octubre", "noviembre", "diciembre"],
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September",
           "October", "November", "December"],
}
ABBREV = {
    "es": {"Sr.": "señor", "Sra.": "señora", "Srta.": "señorita", "Dr.": "doctor", "Dra.": "doctora",
           "Lic.": "licenciado", "Ing.": "ingeniero", "Prof.": "profesor", "Av.": "avenida", "Col.": "colonia",
           "Ud.": "usted", "Uds.": "ustedes", "etc.": "etcétera", "aprox.": "aproximadamente", "p. ej.": "por ejemplo",
           "Núm.": "número", "Tel.": "teléfono", "km": "kilómetros", "kg": "kilos", "cm": "centímetros", "EE. UU.": "Estados Unidos",
           "EE.UU.": "Estados Unidos"},
    "en": {"Mr.": "mister", "Mrs.": "missus", "Ms.": "miz", "Dr.": "doctor", "Prof.": "professor", "St.": "street",
           "Ave.": "avenue", "etc.": "et cetera", "vs.": "versus", "approx.": "approximately", "e.g.": "for example",
           "i.e.": "that is", "km": "kilometers", "kg": "kilograms", "cm": "centimeters", "Jr.": "junior"},
}
WORDS = {
    "es": {"dot": "punto", "slash": "diagonal", "at": "arroba", "dash": "guion", "percent": "por ciento",
           "and": "con", "point": "punto", "minus": "menos", "number": "número"},
    "en": {"dot": "dot", "slash": "slash", "at": "at", "dash": "dash", "percent": "percent",
           "and": "and", "point": "point", "minus": "minus", "number": "number"},
}
CURRENCY = {  # code -> (es singular, es plural, en singular, en plural)
    "MXN": ("peso", "pesos", "peso", "pesos"),
    "USD": ("dólar", "dólares", "dollar", "dollars"),
    "EUR": ("euro", "euros", "euro", "euros"),
}


def _n(value, lang: str, **kw) -> str:
    return num2words(value, lang=lang, **kw)


def _card(value: int, lang: str, before_noun: bool = False) -> str:
    """Cardinal; Spanish drops the final 'o' of 'uno' before a masculine noun (veintiún pesos)."""
    s = _n(value, lang)
    if lang == "es" and before_noun:
        s = re.sub(r"veintiuno$", "veintiún", s)
        s = re.sub(r"\buno$", "un", s)
    return s.replace("-", " ") if lang == "en" else s


def _to_number(raw: str, lang: str) -> float | int:
    """'1,234.50' (MX/US), '1.234,50' (ES), '3,5' (es decimal), '3.5'."""
    if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", raw):
        raw = raw.replace(",", "")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", raw):
        raw = raw.replace(".", "").replace(",", ".")
    elif lang == "es" and re.fullmatch(r"\d+,\d{1,2}", raw):
        raw = raw.replace(",", ".")
    else:
        raw = raw.replace(",", "")
    return float(raw) if "." in raw else int(raw)


def number(raw: str, lang: str) -> str:
    v = _to_number(raw, lang)
    if isinstance(v, float):
        frac = re.sub(r"\D", "", str(raw).replace(",", ".").rsplit(".", 1)[-1])
        digits = " ".join(_n(int(d), lang) for d in frac) if frac.startswith("0") or len(frac) > 2 else _n(int(frac), lang)
        return f"{_card(int(v), lang)} {WORDS[lang]['point']} {digits}"
    return _card(v, lang)


def money(amount: str, code: str, lang: str) -> str:
    v = _to_number(amount, lang)
    whole, cents = int(v), int(round((float(v) - int(v)) * 100))
    es1, esN, en1, enN = CURRENCY[code]
    unit = (es1 if whole == 1 else esN) if lang == "es" else (en1 if whole == 1 else enN)
    if lang == "es" and whole and whole % 1_000_000 == 0:
        unit = "de " + unit  # "un millón de pesos"
    out = f"{_card(whole, lang, before_noun=True)} {unit}"
    if cents:
        c = "centavo" if lang == "es" and cents == 1 else "centavos" if lang == "es" else "cent" if cents == 1 else "cents"
        if code == "EUR" and lang == "es":
            c = "céntimo" if cents == 1 else "céntimos"
        out += f" {WORDS[lang]['and']} {_card(cents, lang, before_noun=True)} {c}"
    return out


def time_of_day(h: int, m: int, ampm: str | None, lang: str) -> str:
    ampm = (ampm or "").lower().replace(".", "").replace(" ", "")
    if lang == "es":
        hour12 = h % 12 or 12
        hs = "una" if hour12 == 1 else _n(hour12, "es")
        art = "la" if hour12 == 1 else "las"
        mins = "en punto" if m == 0 else ("y media" if m == 30 else ("y cuarto" if m == 15 else f"y {_n(m, 'es')}"))
        if ampm == "am" or (not ampm and h < 12 and h >= 6 and h != 0):
            part = " de la mañana" if ampm or h < 12 else ""
        elif ampm == "pm" or h >= 12:
            hh = h + 12 if ampm == "pm" and h < 12 else h
            part = " de la tarde" if hh < 20 else " de la noche"
        else:
            part = " de la madrugada" if ampm == "" and h < 6 else ""
        return f"{art} {hs} {mins}{part}"
    hour = h if ampm else (h % 12 or 12) if h != 0 else 12
    mins = "o'clock" if m == 0 else (f"oh {_n(m, 'en')}" if m < 10 else _card(m, "en"))
    suffix = {"am": " AM", "pm": " PM"}.get(ampm, "")
    if not ampm and m == 0:
        return f"{_card(hour, 'en')} o'clock"
    return f"{_card(hour, 'en')} {mins}{suffix}".replace(" o'clock AM", " AM").replace(" o'clock PM", " PM")


def date(d: int, mo: int, y: int | None, lang: str) -> str:
    if not 1 <= mo <= 12 or not 1 <= d <= 31:
        raise ValueError
    month = MONTHS[lang][mo - 1]
    if lang == "es":
        day = "primero" if d == 1 else _n(d, "es")
        return f"{day} de {month}" + (f" de {_n(y, 'es')}" if y else "")
    out = f"{month} {_n(d, 'en', to='ordinal')}"
    return out + (f", {_n(y, 'en', to='year').replace('-', ' ')}" if y else "")


def url(u: str, lang: str) -> str:
    w = WORDS[lang]
    u = re.sub(r"^(https?://)?(www\.)?", "", u).rstrip("/")
    u = u.replace(".", f" {w['dot']} ").replace("/", f" {w['slash']} ").replace("@", f" {w['at']} ")
    u = re.sub(r"(?<=\w)-(?=\w)", f" {w['dash']} ", u)
    return re.sub(r"\s+", " ", u).strip()


_NUM = r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
_CODES = "MXN|USD|EUR"


def normalize(text: str, lang: str) -> str:
    if lang not in ("es", "en"):
        return text
    w = WORDS[lang]
    # URLs and e-mails
    text = re.sub(r"\b[\w.+-]+@[\w-]+(\.[\w-]+)+\b", lambda m: url(m.group(0), lang), text)
    text = re.sub(r"\b(?:https?://|www\.)\S+|\b[\w-]+\.(?:com|org|net|mx|es|io|ai|dev|app|co|edu|gob)(?:\.[a-z]{2})?(?:/\S*)?",
                  lambda m: url(m.group(0).rstrip(".,;:!?)"), lang) + m.group(0)[len(m.group(0).rstrip(".,;:!?)")):], text)
    # Money: "$1,250.50 MXN", "MXN 1,250", "US$20", "€5", "20 USD", "$20"
    default_code = "MXN" if lang == "es" else "USD"
    text = re.sub(rf"\b({_CODES})\s?\$?\s?({_NUM})", lambda m: money(m.group(2), m.group(1), lang), text)
    unit_words = {"pesos": "MXN", "peso": "MXN", "dólares": "USD", "dólar": "USD", "dollars": "USD", "dollar": "USD",
                  "euros": "EUR", "euro": "EUR"}
    text = re.sub(rf"(US\$|\$|€)\s?({_NUM})(\s?({_CODES})\b|\s(pesos?|dólar(?:es)?|dollars?|euros?)\b)?",
                  lambda m: money(m.group(2), m.group(4) or unit_words.get(m.group(5) or "")
                                  or {"US$": "USD", "€": "EUR"}.get(m.group(1), default_code), lang), text)
    text = re.sub(rf"\b({_NUM})\s?({_CODES})\b", lambda m: money(m.group(1), m.group(2), lang), text)
    text = re.sub(rf"\b({_NUM})\s?(pesos|dólares|dollars|euros)\b",
                  lambda m: f"{number(m.group(1), lang)} {m.group(2)}", text)
    # Dates: ISO 2026-10-08, then d/m/y (es) or m/d/y (en)

    def _date(original, d, mo, y):
        try:
            y = int(y) + (2000 if len(y) == 2 else 0) if y else None
            return date(int(d), int(mo), y, lang)
        except ValueError:
            return original
    text = re.sub(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", lambda m: _date(m.group(0), m.group(3), m.group(2), m.group(1)), text)
    text = re.sub(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{4}|\d{2}))?\b",
                  lambda m: _date(m.group(0), *((m.group(1), m.group(2)) if lang == "es" else (m.group(2), m.group(1))),
                                  m.group(3)), text)
    # Times: 3:30 pm, 15:45, 10:00 a.m.
    def _time(m):
        t = time_of_day(int(m.group(1)), int(m.group(2)), m.group(3), lang)
        if lang == "es" and re.search(r"\b(la|las)\s$", text[:m.start()], re.I):
            t = t.split(" ", 1)[1]  # "a las 3:30" -> no double article
        return t
    text = re.sub(r"\b([01]?\d|2[0-3]):([0-5]\d)(?:\s?([AaPp]\.?\s?[Mm]\.?))?(?=\W|$)", _time, text)
    # Percent
    text = re.sub(rf"({_NUM})\s?%", lambda m: f"{number(m.group(1), lang)} {w['percent']}", text)
    # Ordinals: 1st 2nd 3rd 4th / 1º 1ª 1.º
    if lang == "en":
        text = re.sub(r"\b(\d+)(st|nd|rd|th)\b", lambda m: _n(int(m.group(1)), "en", to="ordinal").replace("-", " "), text)
    else:
        def _ord_es(m):
            s = _n(int(m.group(1)), "es", to="ordinal")
            if m.group(2) == "ª":
                s = re.sub(r"o\b", "a", s)
            return s
        text = re.sub(r"\b(\d+)\.?([ºª°])", _ord_es, text)
    # "No. 5" / "#5"
    text = re.sub(r"(?:\bNo\.|#)\s?(\d+)", lambda m: f"{w['number']} {m.group(1)}", text)
    # Abbreviations (longest first; units only after a number)
    for k in sorted(ABBREV[lang], key=len, reverse=True):
        v = ABBREV[lang][k]
        if k in ("km", "kg", "cm"):
            text = re.sub(rf"(?<=\d)\s?{k}\b", f" {v}", text)
        else:
            text = re.sub(rf"(?<!\w){re.escape(k)}(?=\s|$)", v, text)
    # Negative numbers and remaining numbers
    text = re.sub(rf"(?<![\w\d])-({_NUM})\b", lambda m: f"{w['minus']} {number(m.group(1), lang)}", text)
    text = re.sub(rf"\b({_NUM})\b", lambda m: number(m.group(1), lang), text)
    if lang == "es":  # apocope before a noun: "veintiuno años" -> "veintiún años", "primero lugar" -> "primer lugar"
        text = re.sub(r"\b(veinti)uno(?= [a-záéíóúñ])", r"\1ún", text)
        text = re.sub(r"\b(y |^|\s)uno(?= [a-záéíóúñ])", r"\1un", text)
        text = re.sub(r"\b(prim|terc)ero(?= (?!de\b)[a-záéíóúñ])", r"\1er", text)
    return re.sub(r"\s{2,}", " ", text).strip()
