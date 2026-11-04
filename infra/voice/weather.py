"""Current weather for a Croatian city from Open-Meteo (no API key).

The spoken answer is filled in from a template, not written by the LLM: a small
model would make up the numbers. Open-Meteo geocodes the city name, then gives the
current temperature, weather code and wind speed.
"""
import os
import re
import unicodedata

import httpx

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
DEFAULT_CITY = os.environ.get("WEATHER_CITY", "Osijek")

WEATHER_RE = re.compile(r"\b(?:vrijem\w*|temperatur\w*|stupnjev\w*|kiš\w*|kis\w*|prognoz\w*)\b", re.IGNORECASE)
CITY_RE = re.compile(r"\b(?:u|za|iz)\s+(\w+)", re.IGNORECASE)

# Locative ("u Osijeku") -> nominative, for the geocoder. Keys have no diacritics.
# Only common cities; any other word is passed to the geocoder as it is.
LOCATIVE = {
    "osijeku": "Osijek",
    "zagrebu": "Zagreb",
    "splitu": "Split",
    "rijeci": "Rijeka",
    "zadru": "Zadar",
    "puli": "Pula",
    "varazdinu": "Varaždin",
    "dubrovniku": "Dubrovnik",
    "sibeniku": "Šibenik",
    "karlovcu": "Karlovac",
    "vukovaru": "Vukovar",
    "vinkovcima": "Vinkovci",
    "retkovcima": "Retkovci",
    "prkovcima": "Prkovci",
}


def _key(word: str) -> str:
    return unicodedata.normalize("NFKD", word).encode("ascii", "ignore").decode().lower()


def city_from(text: str) -> str:
    m = CITY_RE.search(text)
    if not m:
        return DEFAULT_CITY
    return LOCATIVE.get(_key(m.group(1)), m.group(1))


def describe(code: int) -> str:
    """WMO weather code -> a short Croatian phrase."""
    if code == 0:
        return "vedro"
    if code in (1, 2):
        return "djelomično oblačno"
    if code == 3:
        return "oblačno"
    if code in (45, 48):
        return "magla"
    if 51 <= code <= 67 or 80 <= code <= 82:
        return "kiša"
    if 71 <= code <= 77 or code in (85, 86):
        return "snijeg"
    if code >= 95:
        return "grmljavina"
    return "promjenjivo"


def number_words(value: float) -> str:
    n = round(value)
    return f"minus {abs(n)}" if n < 0 else str(n)


async def answer(http: httpx.AsyncClient, text: str) -> str:
    city = city_from(text)
    r = await http.get(GEO_URL, params={"name": city, "count": 1, "language": "hr"})
    r.raise_for_status()
    results = r.json().get("results")
    if not results:
        return f"Nisam pronašao grad {city}."
    place = results[0]

    r = await http.get(FORECAST_URL, params={
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "current": "temperature_2m,weather_code,wind_speed_10m",
        "timezone": "Europe/Zagreb",
    })
    r.raise_for_status()
    cur = r.json()["current"]
    return (f"{place['name']}: trenutno {number_words(cur['temperature_2m'])} stupnjeva, "
            f"{describe(int(cur['weather_code']))}. "
            f"Vjetar je {number_words(cur['wind_speed_10m'])} kilometara na sat.")
