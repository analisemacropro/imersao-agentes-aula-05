"""Tools de coleta do IBGE (portal SIDRA), com metadados.

O IBGE é diferente do Banco Central num ponto que decide o desenho: uma série
da SIDRA não é um código só, é uma COMBINAÇÃO — tabela + variável +
(opcional) classificação/categoria. Uma combinação inválida não dá erro; volta
vazia ou volta outra coisa. Por isso o IBGE precisa de guardrail.

A boa notícia é que a SIDRA tem uma API de METADADOS que descreve cada tabela:
quais variáveis existem, quais classificações, quais categorias. Então o agente
pode olhar o cardápio antes de pedir. São duas tools:

  - `descrever_tabela_sidra` — lê os metadados e devolve o cardápio da tabela.
  - `coletar_sidra` — coleta a combinação, validando-a contra os metadados antes.
"""

import requests
from langchain_core.tools import tool

META = "https://servicodados.ibge.gov.br/api/v3/agregados/{tabela}/metadados"


def _metadados(tabela: str) -> dict:
    resp = requests.get(META.format(tabela=tabela), timeout=20)
    # Uma tabela inexistente faz a SIDRA devolver 500/404 — traduzimos para uma
    # mensagem clara, em vez de propagar o erro HTTP cru para o agente.
    if resp.status_code >= 400:
        raise ValueError(
            f"não encontrei a tabela {tabela} na SIDRA (a API respondeu "
            f"{resp.status_code}). Confira o código da tabela no site do IBGE."
        )
    return resp.json()


@tool
def descrever_tabela_sidra(tabela: str) -> dict:
    """Descreve uma tabela da SIDRA: variáveis e classificações válidas.

    Use ANTES de coletar, quando não tiver certeza da combinação de códigos
    (variável, classificação, categoria) de uma tabela do IBGE. Devolve o nome
    da tabela e o "cardápio": as variáveis disponíveis (id e nome) e as
    classificações com suas categorias. É o que evita pedir uma combinação que
    não existe. Ex.: a tabela 1737 é o IPCA; a 7060 é o IPCA por grupo.
    """
    m = _metadados(tabela)
    variaveis = [{"id": str(v["id"]), "nome": v["nome"]} for v in m.get("variaveis", [])]
    classificacoes = []
    for c in m.get("classificacoes", []):
        cats = [{"id": str(cat["id"]), "nome": cat["nome"]} for cat in c.get("categorias", [])]
        classificacoes.append({
            "id": str(c["id"]),
            "nome": c["nome"],
            # Tabelas como a 7060 têm centenas de categorias; cortamos a amostra
            # para o agente ver o formato sem estourar o contexto.
            "categorias_amostra": cats[:12],
            "total_categorias": len(cats),
        })
    return {
        "tabela": tabela,
        "nome": m.get("nome"),
        "periodo": m.get("periodicidade"),
        "variaveis": variaveis,
        "classificacoes": classificacoes,
    }


def _validar_combinacao(tabela: str, variavel: str, classificacao: str, categoria: str) -> None:
    """Confere a combinação contra os metadados. Levanta erro claro se inválida.

    É o guardrail do IBGE: em vez de buscar uma combinação que volta vazia,
    paramos antes e dizemos exatamente o que está errado e o que é válido.
    """
    # Classificação e categoria andam juntas: uma sem a outra é pedido pela
    # metade, e a SIDRA ignoraria em silêncio (devolvendo o índice geral em vez
    # do grupo). Recusamos antes que o erro passe despercebido.
    if bool(classificacao) != bool(categoria):
        raise ValueError(
            "para um grupo, passe classificacao E categoria juntas "
            f"(recebi classificacao='{classificacao}', categoria='{categoria}'). "
            f"Use descrever_tabela_sidra({tabela}) para ver os pares válidos."
        )

    m = _metadados(tabela)
    ids_var = {str(v["id"]) for v in m.get("variaveis", [])}
    if variavel not in ids_var:
        raise ValueError(
            f"variável '{variavel}' não existe na tabela {tabela}. "
            f"Variáveis válidas: {sorted(ids_var)}. "
            f"Use descrever_tabela_sidra({tabela}) para ver os nomes."
        )
    if classificacao:
        classes = {str(c["id"]): c for c in m.get("classificacoes", [])}
        if classificacao not in classes:
            raise ValueError(
                f"classificação '{classificacao}' não existe na tabela {tabela}. "
                f"Classificações válidas: {sorted(classes)}."
            )
        if categoria:
            ids_cat = {str(cat["id"]) for cat in classes[classificacao].get("categorias", [])}
            if categoria not in ids_cat:
                raise ValueError(
                    f"categoria '{categoria}' não existe na classificação "
                    f"{classificacao} (tabela {tabela}). Use descrever_tabela_sidra."
                )


@tool
def coletar_sidra(tabela: str = "1737", variavel: str = "63",
                  classificacao: str = "", categoria: str = "", meses: int = 12) -> dict:
    """Coleta um índice oficial do IBGE pelo portal SIDRA.

    Aceita a combinação livre: `tabela`, `variavel` e, opcionalmente,
    `classificacao` + `categoria` (para um grupo específico). A combinação é
    CONFERIDA contra os metadados antes de buscar; se for inválida, a tool diz
    o que está errado, em vez de devolver dados vazios.

    Padrões: tabela 1737 (IPCA), variável 63 (variação mensal). Para um grupo
    (ex.: Alimentação na tabela 7060), passe classificacao e categoria — use
    descrever_tabela_sidra primeiro para descobrir os códigos certos.

    Devolve {tabela_nome, pontos: [{data, valor}]}. Prefira esta tool para o
    IPCA oficial e seus grupos; para Selic e câmbio, use a tool do SGS.
    """
    import sidrapy

    _validar_combinacao(tabela, variavel, classificacao, categoria)

    kwargs = dict(
        table_code=tabela, territorial_level="1",
        ibge_territorial_code="all", variable=variavel, period=f"last {meses}",
    )
    if classificacao and categoria:
        kwargs["classifications"] = {classificacao: categoria}

    # sidrapy devolve um DataFrame: a 1ª linha é o cabeçalho (descrições das
    # colunas), as demais são os dados. Colunas-chave: V=valor, D2C=mês
    # ("AAAAMM"), D3N=nome da variável, D4N=nome da categoria.
    df = sidrapy.get_table(**kwargs)
    linhas = df.iloc[1:].to_dict("records")

    # A SIDRA marca valor ausente com vários sentinelas ('...', '..', '-', 'X')
    # — e o mês mais recente costuma vir assim, antes da divulgação. Em vez de
    # listar cada sentinela (e quebrar quando aparece um novo), tentamos
    # converter e PULAMOS o que não for número. Foi um '..' não previsto que
    # derrubava a coleta da PMC.
    pontos = []
    for l in linhas:
        # D2C é o mês no formato "AAAAMM" (6 dígitos). Se vier diferente, a data
        # montada seria inválida — pulamos em vez de gerar lixo.
        d2c = str(l.get("D2C", ""))
        if len(d2c) != 6 or not d2c.isdigit():
            continue
        try:
            valor = float(str(l["V"]).replace(",", "."))
        except (ValueError, TypeError):
            continue
        pontos.append({"data": f"{d2c[:4]}-{d2c[4:]}-01", "valor": valor})
    # Monta um nome legível a partir da variável e, se houver, da categoria.
    primeira = linhas[0] if linhas else {}
    nome = primeira.get("D3N", f"tabela {tabela}")
    if primeira.get("D4N"):
        nome += f" — {primeira['D4N']}"
    return {"tabela_nome": nome, "pontos": pontos}
