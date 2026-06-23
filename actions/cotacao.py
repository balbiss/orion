from __future__ import annotations

import json
import urllib.request

_ALIASES: dict[str, str] = {
    "dólar":   "USD-BRL",
    "dolar":   "USD-BRL",
    "usd":     "USD-BRL",
    "euro":    "EUR-BRL",
    "eur":     "EUR-BRL",
    "bitcoin": "BTC-BRL",
    "btc":     "BTC-BRL",
    "ethereum":"ETH-BRL",
    "eth":     "ETH-BRL",
    "libra":   "GBP-BRL",
    "gbp":     "GBP-BRL",
    "iene":    "JPY-BRL",
    "jpy":     "JPY-BRL",
    "peso":    "ARS-BRL",
    "ars":     "ARS-BRL",
}

_DEFAULT = ["USD-BRL", "EUR-BRL", "BTC-BRL"]


def cotacao(parameters: dict, player=None, **_) -> str:
    moedas_raw = parameters.get("moedas", [])
    if isinstance(moedas_raw, str):
        moedas_raw = [m.strip() for m in moedas_raw.split(",")]

    pairs = (
        [_ALIASES.get(m.lower().strip(), m.upper().strip()) for m in moedas_raw]
        if moedas_raw else _DEFAULT
    )
    pairs_str = ",".join(pairs)

    print(f"[Cotacao] {pairs_str}")
    if player:
        player.write_log(f"[Cotacao] {pairs_str}")

    try:
        url = f"https://economia.awesomeapi.com.br/json/last/{pairs_str}"
        with urllib.request.urlopen(url, timeout=8) as r:
            data = json.loads(r.read())
    except Exception as e:
        return f"Erro ao buscar cotações: {e}"

    lines = []
    for val in data.values():
        name   = val.get("name", "")
        bid    = float(val.get("bid", 0))
        pct    = float(val.get("pctChange", 0))
        sinal  = "+" if pct >= 0 else ""
        lines.append(f"• {name}: R$ {bid:,.2f} ({sinal}{pct:.2f}% hoje)")

    if not lines:
        return "Nenhuma cotação retornada."

    return "Cotações agora:\n" + "\n".join(lines)
