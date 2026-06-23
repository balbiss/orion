from __future__ import annotations

import json
import urllib.request
import urllib.parse
from pathlib import Path


def _get_key() -> str:
    cfg = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
    return json.loads(cfg.read_text(encoding="utf-8")).get("openweather_api_key", "")


def weather_action(parameters: dict, player=None, **_) -> str:
    city = parameters.get("city", "").strip()
    if not city:
        return "Me diga a cidade para o clima."

    key = _get_key()
    if not key or key == "SUA_KEY_AQUI":
        return "Chave OpenWeatherMap não configurada. Adicione 'openweather_api_key' no config/api_keys.json."

    url = (
        "https://api.openweathermap.org/data/2.5/weather"
        f"?q={urllib.parse.quote(city)}&appid={key}&units=metric&lang=pt_br"
    )
    print(f"[Weather] Buscando clima para: {city}")
    if player:
        player.write_log(f"[Weather] {city}")

    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return f"Cidade '{city}' não encontrada. Tente com nome em inglês ou verifique a grafia."
        return f"Erro na API de clima: {e}"
    except Exception as e:
        return f"Erro ao buscar clima: {e}"

    desc      = data["weather"][0]["description"].capitalize()
    temp      = data["main"]["temp"]
    feels     = data["main"]["feels_like"]
    temp_min  = data["main"]["temp_min"]
    temp_max  = data["main"]["temp_max"]
    humidity  = data["main"]["humidity"]
    wind      = data["wind"]["speed"]
    city_name = data["name"]
    country   = data["sys"]["country"]

    return (
        f"Clima em {city_name}, {country}: {desc}. "
        f"Temperatura atual {temp:.0f}°C, sensação térmica {feels:.0f}°C. "
        f"Mínima {temp_min:.0f}°C, máxima {temp_max:.0f}°C. "
        f"Umidade {humidity}%, vento {wind:.1f} m/s."
    )
