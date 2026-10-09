import pytest

from voicer.text.normalize import normalize


@pytest.mark.parametrize("src,want", [
    ("Tengo 21 años.", "Tengo veintiún años."),
    ("Página 21.", "Página veintiuno."),
    ("Compré 1 libro", "Compré un libro"),
    ("Cuesta $1,250.50 MXN.", "Cuesta mil doscientos cincuenta pesos con cincuenta centavos."),
    ("Son 21 pesos", "Son veintiún pesos"),
    ("Pagué $21.", "Pagué veintiún pesos."),
    ("Vale 20 USD", "Vale veinte dólares"),
    ("Vale US$1", "Vale un dólar"),
    ("La cita es a las 3:30 pm", "La cita es a las tres y media de la tarde"),
    ("Abrimos 9:00", "Abrimos las nueve en punto de la mañana"),
    ("Nació el 08/10/2026", "Nació el ocho de octubre de dos mil veintiséis"),
    ("Fecha 2026-01-01", "Fecha primero de enero de dos mil veintiséis"),
    ("Descuento de 15%", "Descuento de quince por ciento"),
    ("El Sr. Pérez y la Dra. López", "El señor Pérez y la doctora López"),
    ("Visita www.fami.mx/ayuda", "Visita fami punto mx diagonal ayuda"),
    ("Escribe a hola@ejemplo.mx", "Escribe a hola arroba ejemplo punto mx"),
    ("Pi es 3,14", "Pi es tres punto catorce"),
    ("Está a 5 km", "Está a cinco kilómetros"),
    ("el 1º lugar y la 2ª vez", "el primer lugar y la segunda vez"),
])
def test_es(src, want):
    assert normalize(src, "es") == want


@pytest.mark.parametrize("src,want", [
    ("It costs $1,250.50.", "It costs one thousand, two hundred and fifty dollars and fifty cents."),
    ("Pay 300 MXN", "Pay three hundred pesos"),
    ("Meet at 3:05 pm", "Meet at three oh five PM"),
    ("Meet at 10:00", "Meet at ten o'clock"),
    ("Born 10/08/2026", "Born October eighth, twenty twenty six"),
    ("Up 3.5%", "Up three point five percent"),
    ("Mr. Smith lives on Main St.", "mister Smith lives on Main street"),
    ("Go to https://example.com/docs.", "Go to example dot com slash docs."),
    ("The 21st time", "The twenty first time"),
    ("It is -5 degrees", "It is minus five degrees"),
])
def test_en(src, want):
    assert normalize(src, "en") == want


def test_plan_normalizes_per_language():
    from voicer.tts import plan

    p = plan("Hola, cuesta $21 pesos hoy. It costs $5 today.")
    assert [(s.text, s.lang) for s in p] == [("Hola, cuesta veintiún pesos hoy.", "es"), ("It costs five dollars today.", "en")]


@pytest.mark.gpu
def test_spoken_money_and_time(tmp_out):
    from conftest import similar, transcribe
    from voicer import audio, tts

    v = {"id": "k", "engine": "kokoro", "engine_voice": "ef_dora", "language": "es"}
    out = tts.speak("La cita es el 08/10/2026 a las 3:30 pm y cuesta $1,250 MXN.", v, "es")
    heard = normalize(transcribe(audio.write_wav(out, tmp_out / "norm.wav"), "es"), "es")
    want = "La cita es el ocho de octubre de dos mil veintiséis a las tres y media de la tarde y cuesta mil doscientos cincuenta pesos."
    assert similar(heard, want) > 0.6, heard
