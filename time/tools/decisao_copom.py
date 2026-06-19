"""Tool da Selic: a meta vigente e a última decisão do Copom.

A Selic é diferente dos outros indicadores, e tratá-la igual engana. Ela não
tem "variação mensal": é uma META que fica parada por meses e só muda quando o
Copom decide, numa reunião. Calcular M/M, 12m ou média móvel dela dá quase tudo
zero (porque o nível não mudou no mês) ou números sem leitura econômica.

O que importa na Selic é outra coisa: qual é a meta agora, e qual foi a última
mudança (de quanto para quanto, quando, quantos pontos). É isso que esta tool
extrai — direto da série oficial do Banco Central (SGS 432, a meta definida pelo
Copom). A série vem diária, com o valor repetido todo dia; nós pegamos só os
DEGRAUS (os pontos onde a meta mudou), e cada degrau é uma decisão do Copom.
"""

from datetime import datetime, timedelta

from langchain_core.tools import tool

from tools.bcb_sgs import _com_retry

CODIGO_META_SELIC = 432  # série SGS da meta Selic definida pelo Copom


def _coletar_432(inicio: str) -> list[dict]:
    """Lê a meta Selic (SGS 432) por intervalo de datas, em dicts ordenáveis."""
    from bcb import sgs

    df = sgs.get({"serie": CODIGO_META_SELIC}, start=inicio)
    return [{"data": idx.date().isoformat(), "valor": float(linha.iloc[0])}
            for idx, linha in df.iterrows()]


@tool
def decisao_copom() -> dict:
    """Devolve a meta Selic vigente e a última decisão do Copom.

    Use para a SELIC, em vez de calcular variações: a Selic é uma meta que só
    muda em reunião do Copom, então a leitura certa é a taxa atual e a última
    mudança — não variação mensal/12 meses.

    Lê a série oficial (SGS 432) e extrai os "degraus" (onde a meta mudou).
    Devolve {meta_atual, desde, mudanca: {de, para, delta_pp, data},
    historico: [{data, valor}]} com as últimas decisões.
    """
    # Janela de ~3 anos: pega vários degraus sem estourar o limite de 10 anos
    # do SGS para séries diárias. (A 432 é diária; o valor se repete entre as
    # reuniões.) `_com_retry` dá a mesma resiliência de rede das outras coletas.
    inicio = (datetime.now().date() - timedelta(days=3 * 366)).isoformat()
    try:
        pontos = _com_retry(lambda: _coletar_432(inicio))
    except Exception as erro:
        return {"erro": f"não consegui ler a meta Selic (SGS 432): {erro}"}

    pontos = sorted(pontos, key=lambda p: p["data"])
    if not pontos:
        return {"erro": "a série da meta Selic voltou vazia."}

    # Degraus: só os pontos onde o valor mudou em relação ao anterior. Cada um é
    # uma decisão do Copom (corte, alta ou manutenção que encerrou um ciclo).
    degraus = [pontos[0]]
    for p in pontos[1:]:
        if p["valor"] != degraus[-1]["valor"]:
            degraus.append(p)

    atual = degraus[-1]
    resultado = {
        "meta_atual": atual["valor"],
        "desde": atual["data"],
        "historico": degraus[-6:],  # as últimas decisões, para contexto
    }
    # A última mudança (se houver um degrau anterior para comparar).
    if len(degraus) >= 2:
        anterior = degraus[-2]
        resultado["mudanca"] = {
            "de": anterior["valor"],
            "para": atual["valor"],
            "delta_pp": round(atual["valor"] - anterior["valor"], 2),
            "data": atual["data"],
        }
    return resultado
