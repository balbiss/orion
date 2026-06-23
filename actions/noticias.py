from __future__ import annotations

import json
import urllib.request
import urllib.parse
from pathlib import Path


def _get_key() -> str:
    cfg = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
    return json.loads(cfg.read_text(encoding="utf-8")).get("newsapi_key", "")


def noticias(parameters: dict, player=None, **_) -> str:
    query    = parameters.get("query", "").strip()
    category = parameters.get("category", "").strip()
    max_res  = min(int(parameters.get("max", 5)), 10)

    key = _get_key()
    if not key or key == "SUA_KEY_AQUI":
        return "Chave NewsAPI não configurada. Adicione 'newsapi_key' no config/api_keys.json."

    if query:
        url = (
            "https://newsapi.org/v2/everything"
            f"?q={urllib.parse.quote(query)}&language=pt"
            f"&sortBy=publishedAt&pageSize={max_res}&apiKey={key}"
        )
    else:
        cat = f"&category={category}" if category else ""
        url = (
            f"https://newsapi.org/v2/top-headlines"
            f"?country=br{cat}&pageSize={max_res}&apiKey={key}"
        )

    print(f"[Noticias] query='{query}' category='{category}'")
    if player:
        player.write_log(f"[Noticias] {query or category or 'Brasil'}")

    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            data = json.loads(r.read())
    except Exception as e:
        return f"Erro ao buscar notícias: {e}"

    if data.get("status") != "ok":
        return f"Erro NewsAPI: {data.get('message', 'desconhecido')}"

    articles = data.get("articles", [])
    if not articles:
        return "Nenhuma notícia encontrada."

    tema = f" sobre '{query}'" if query else (f" de {category}" if category else " do Brasil")
    lines = [f"Principais notícias{tema}:"]
    for i, a in enumerate(articles[:max_res], 1):
        title  = (a.get("title") or "").split(" - ")[0].strip()
        source = a.get("source", {}).get("name", "")
        if title:
            lines.append(f"{i}. {title} [{source}]")

    return "\n".join(lines)
