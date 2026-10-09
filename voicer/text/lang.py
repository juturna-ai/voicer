"""Fast es/en language detection for single sentences (no model, no download)."""
from __future__ import annotations

import re

ES_WORDS = set("""
de la que el en y a los se del las un por con no una su para es al lo como más pero sus le ya o este sí
porque esta entre cuando muy sin sobre también me hasta hay donde quien desde todo nos durante todos uno
les ni contra otros ese eso ante ellos e esto mí antes algunos qué unos yo otro otras otra él tanto esa
estos mucho quienes nada muchos cual poco ella estar estas algunas algo nosotros mi mis tú te ti tu tus
ellas nosotras vosotros os mío mía tuyo suyo nuestro estoy estás está estamos están soy eres somos son
fue era hola gracias buenos buenas días tardes noches cómo dónde cuándo cuánto bien mal hoy mañana ayer
hace tiene tengo puede puedo quiero necesito vamos usted ustedes señor señora aquí allí ahora siempre
nunca también adiós favor
""".split())
EN_WORDS = set("""
the be to of and a in that have i it for not on with he as you do at this but his by from they we say
her she or an will my one all would there their what so up out if about who get which go me when make
can like time no just him know take people into year your good some could them see other than then now
look only come its over think also back after use two how our work first well way even new want because
any these give day most us is are was were been has had did does hello thanks thank please yes where
why very today tomorrow yesterday morning evening night here let's i'm you're it's don't can't
""".split())
ES_CHARS = re.compile(r"[ñáéíóúü¿¡]", re.I)
WORD = re.compile(r"[a-záéíóúüñ']+", re.I)


def detect(text: str, default: str = "en") -> str:
    """Return 'es' or 'en'. Ties and unknown text fall back to `default`."""
    words = [w.lower() for w in WORD.findall(text)]
    es = sum(w in ES_WORDS for w in words) + 2 * len(ES_CHARS.findall(text))
    en = sum(w in EN_WORDS for w in words)
    if es == en:
        return default
    return "es" if es > en else "en"
