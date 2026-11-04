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


# SpeechT5 has no digits in its vocabulary and drops them, so numbers are spelled out.
_ONES = ["nula", "jedan", "dva", "tri", "četiri", "pet", "šest", "sedam", "osam", "devet",
         "deset", "jedanaest", "dvanaest", "trinaest", "četrnaest", "petnaest", "šesnaest",
         "sedamnaest", "osamnaest", "devetnaest"]
_TENS = {2: "dvadeset", 3: "trideset", 4: "četrdeset", 5: "pedeset", 6: "šezdeset",
         7: "sedamdeset", 8: "osamdeset", 9: "devedeset"}
_HUNDREDS = {1: "sto", 2: "dvjesto", 3: "tristo", 4: "četiristo", 5: "petsto",
             6: "šesto", 7: "sedamsto", 8: "osamsto", 9: "devetsto"}


def hr_int(n: int) -> str:
    """Croatian words for a whole number from -999 to 999 (the range of weather values)."""
    if n < 0:
        return "minus " + hr_int(-n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return _TENS[tens] + ("" if ones == 0 else " " + _ONES[ones])
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        return _HUNDREDS[hundreds] + ("" if rest == 0 else " " + hr_int(rest))
    return str(n)


def _unit(n: int, one: str, few: str, many: str) -> str:
    """Croatian noun form for a count: 1 stupanj, 2 stupnja, 5 stupnjeva (11 and 12-14 take 'many')."""
    last, last_two = n % 10, n % 100
    if last == 1 and last_two != 11:
        return one
    if last in (2, 3, 4) and last_two not in (12, 13, 14):
        return few
    return many


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
    temp = round(cur["temperature_2m"])
    wind = round(cur["wind_speed_10m"])
    temp_unit = _unit(abs(temp), "stupanj", "stupnja", "stupnjeva")
    wind_unit = _unit(abs(wind), "kilometar", "kilometra", "kilometara")
    return (f"{place['name']}: trenutno {hr_int(temp)} {temp_unit}, "
            f"{describe(int(cur['weather_code']))}. "
            f"Vjetar je {hr_int(wind)} {wind_unit} na sat.")
