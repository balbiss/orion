from __future__ import annotations

import json
import urllib.request


def _clean(cep: str) -> str:
    return "".join(c for c in cep if c.isdigit())


def _viacep(cep: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"https://viacep.com.br/ws/{cep}/json/", timeout=8) as r:
            data = json.loads(r.read())
            return None if "erro" in data else data
    except Exception:
        return None


def _ibge_estado(uf: str) -> str:
    try:
        url = f"https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf.upper()}"
        with urllib.request.urlopen(url, timeout=8) as r:
            d = json.loads(r.read())
            return f"{d['nome']} — Região {d['regiao']['nome']}"
    except Exception:
        return uf


def _ibge_cidades(uf: str) -> str:
    try:
        url = f"https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf.upper()}/municipios"
        with urllib.request.urlopen(url, timeout=8) as r:
            cities = json.loads(r.read())
        estado = _ibge_estado(uf)
        return f"{estado} tem {len(cities)} municípios."
    except Exception as e:
        return f"Erro IBGE: {e}"


def _ibge_estados() -> str:
    try:
        with urllib.request.urlopen(
            "https://servicodados.ibge.gov.br/api/v1/localidades/estados?orderBy=nome",
            timeout=8,
        ) as r:
            estados = json.loads(r.read())
        lines = [f"• {e['sigla']} — {e['nome']}" for e in estados]
        return "Estados brasileiros:\n" + "\n".join(lines)
    except Exception as e:
        return f"Erro IBGE: {e}"


def consulta_cep(parameters: dict, player=None, **_) -> str:
    action = parameters.get("action", "cep").lower().strip()

    print(f"[CEP] {action}  {parameters}")
    if player:
        player.write_log(f"[CEP] {action}")

    if action in ("cep", "buscar", "endereço", "endereco", "busca"):
        cep = _clean(parameters.get("cep", ""))
        if len(cep) != 8:
            return "CEP inválido — precisa ter 8 dígitos."

        data = _viacep(cep)
        if not data:
            return f"CEP {cep} não encontrado na base ViaCEP."

        rua    = data.get("logradouro") or "Não informado"
        bairro = data.get("bairro")     or "Não informado"
        cidade = data.get("localidade") or ""
        uf     = data.get("uf")         or ""
        estado = _ibge_estado(uf) if uf else ""

        return (
            f"CEP {cep[:5]}-{cep[5:]}:\n"
            f"Logradouro: {rua}\n"
            f"Bairro: {bairro}\n"
            f"Cidade: {cidade} / {estado}"
        )

    if action in ("estado", "uf"):
        uf = parameters.get("uf", "").strip()
        if not uf:
            return _ibge_estados()
        return _ibge_cidades(uf)

    if action in ("estados", "listar_estados"):
        return _ibge_estados()

    return f"Ação desconhecida: '{action}'. Use: cep, estado, estados."
