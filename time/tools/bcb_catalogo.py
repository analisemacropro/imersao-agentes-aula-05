"""Resolve o NOME de uma série do SGS a partir do código.

O problema: a API de dados do Banco Central (`/dados/serie/bcdata.sgs.N`)
devolve só data e valor — nunca o nome da série. Então, se o usuário pede a
série 433, o agente busca números sem nenhuma forma de confirmar que é mesmo
o IPCA. Esse é o ponto cego do BCB (diferente do IBGE, que tem metadados).

A defesa é resolver o nome em cascata, do mais confiável ao menos:

  1. CATÁLOGO CURADO — um punhado de séries que a imersão usa, com nome certo.
  2. PORTAL DE DADOS ABERTOS (CKAN) — cobre ~3,5 mil séries publicadas como
     dataset; resolve mais alguns nomes, mas NÃO cobre todas (~24% do SGS, e
     sem o próprio 433). É reforço, não garantia.
  3. NOME DADO PELO USUÁRIO — quando ele passa o código junto com o nome.

Se nenhuma das três resolve, o nome fica desconhecido, e quem chama decide o
que fazer (a tool de coleta exige o nome nesse caso — ver bcb_sgs.py).
"""

import urllib.parse
import urllib.request

import requests

# 1) Catálogo curado: as séries da imersão, com o nome oficial. Editável à mão,
#    é a fonte mais confiável porque foi conferida por uma pessoa.
CATALOGO = {
    433: "IPCA — variação mensal (%)",
    432: "Meta Selic definida pelo Copom (% a.a.)",
    1: "Dólar de venda (R$/US$)",
    4389: "Selic acumulada no mês anualizada (% a.a.)",
    13522: "IPCA acumulado em 12 meses (%)",
    189: "IGP-M — variação mensal (%)",
    24364: "IBC-Br — índice (dessazonalizado)",
}

# Os atalhos por nome amigável que o agente pode usar sem decorar o código.
ATALHOS = {"ipca": 433, "selic": 432, "cambio": 1, "câmbio": 1, "igpm": 189}

# Cache em memória para não repetir a consulta ao CKAN no mesmo processo.
_cache_ckan: dict[int, str | None] = {}

CKAN = "https://dadosabertos.bcb.gov.br/api/3/action/package_search"


def _nome_via_ckan(codigo: int) -> str | None:
    """Reforço: tenta o nome no portal de dados abertos. Pode não achar."""
    if codigo in _cache_ckan:
        return _cache_ckan[codigo]
    nome = None
    try:
        q = urllib.parse.urlencode({"fq": f"codigo_sgs:{codigo}", "rows": 1})
        resp = requests.get(f"{CKAN}?{q}", timeout=15)
        resp.raise_for_status()
        achados = resp.json().get("result", {}).get("results", [])
        if achados:
            nome = achados[0].get("title")
    except Exception:
        nome = None  # rede/portal fora do ar não é fatal: seguimos sem o nome
    _cache_ckan[codigo] = nome
    return nome


def resolver_nome(codigo: int, nome_usuario: str | None = None) -> str | None:
    """Devolve o nome da série, ou None se nenhuma fonte souber.

    Cascata: catálogo curado → CKAN → nome dado pelo usuário. O nome do usuário
    entra por último porque é o menos verificável (ele pode se enganar), mas
    ainda é melhor que `None` quando as fontes oficiais não cobrem a série.
    """
    if codigo in CATALOGO:
        return CATALOGO[codigo]
    via_ckan = _nome_via_ckan(codigo)
    if via_ckan:
        return via_ckan
    return nome_usuario  # pode ser None — aí o nome é mesmo desconhecido
