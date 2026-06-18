"""Tool de coleta do Banco Central (sistema SGS).

Uma tool é uma função comum com uma descrição em linguagem natural. É a
docstring que o agente lê para decidir QUANDO chamar a ferramenta — por isso
ela é escrita com o mesmo cuidado de um prompt.

Esta tool aceita INPUT LIVRE: o usuário pode pedir um atalho ("ipca") ou
passar o código cru de qualquer série do SGS. Como a API do BCB não devolve o
nome da série, há um guardrail: para um código fora do catálogo, o usuário
precisa dizer o nome junto — senão a tool recusa e pede o nome, em vez de
coletar números sem saber o que são.

A coleta tem duas formas: a direta (python-bcb) e a de reserva (API HTTP). Se
a primeira falhar, a tool cai na segunda sozinha.
"""

import logging
import time
from datetime import datetime, timedelta

import requests
from langchain_core.tools import tool

from tools.bcb_catalogo import ATALHOS, resolver_nome

log = logging.getLogger("tools.bcb_sgs")

URL_SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json"


def _com_retry(funcao, tentativas: int = 3):
    """Tenta de novo com backoff — a defesa contra a falha de rede passageira.

    A espera dobra a cada tentativa (1s, 2s, 4s) para não martelar uma API que
    já está sofrendo. Se todas falharem, propaga o último erro.
    """
    for tentativa in range(1, tentativas + 1):
        try:
            return funcao()
        except (requests.RequestException, ConnectionError):
            if tentativa == tentativas:
                raise
            time.sleep(2 ** (tentativa - 1))  # 1s, 2s, 4s


def _via_lib(codigo: int, ultimos: int) -> list[dict]:
    """Forma direta: usa a python-bcb. Pode falhar se a lib mudar.

    Armadilha do SGS: o atalho `last=N` é recusado pelo servidor quando N passa
    de 20 ("a quantidade máxima de valores deve ser 20"). Para trazer mais
    histórico, pedimos por INTERVALO DE DATAS (que não tem esse teto) e cortamos
    os últimos N no fim. Calculamos a data inicial folgada (N meses para trás,
    com margem) para garantir que os N pontos venham completos.
    """
    from bcb import sgs

    if ultimos <= 20:
        df = sgs.get({"serie": codigo}, last=ultimos)
    else:
        # ~N meses para trás, com folga, para uma série mensal.
        inicio = (datetime.now().date()
                  - timedelta(days=int((ultimos + 6) * 31)))
        df = sgs.get({"serie": codigo}, start=inicio.isoformat())

    # A lib devolve um DataFrame indexado por data; normalizamos para dicts e,
    # se viemos pelo intervalo, ficamos só com os últimos N pontos.
    pontos = [
        {"data": idx.date().isoformat(), "valor": float(linha.iloc[0])}
        for idx, linha in df.iterrows()
    ]
    pontos = pontos[-ultimos:]

    # Sanidade do corte: para uma série mensal, N pontos deveriam cobrir ~N
    # meses. Se cobrem muito mais (furos na série ou frequência diferente da
    # mensal), avisamos no log — as variações sairiam de uma janela enganosa.
    if len(pontos) >= 2:
        d0 = datetime.fromisoformat(pontos[0]["data"]).date()
        d1 = datetime.fromisoformat(pontos[-1]["data"]).date()
        meses_span = (d1.year - d0.year) * 12 + (d1.month - d0.month) + 1
        if meses_span > len(pontos) * 1.5:
            log.warning("série %s esparsa: %d pontos cobrindo ~%d meses "
                        "(possível furo ou frequência não-mensal)",
                        codigo, len(pontos), meses_span)
    return pontos


def _via_http(codigo: int, ultimos: int) -> list[dict]:
    """Reserva: bate direto na API SGS, sem biblioteca nenhuma.

    Converte ponto a ponto com try/except: se um valor vier como sentinela de
    ausente ('...', vazio) ou a data num formato inesperado, PULAMOS aquele
    ponto em vez de abortar a coleta inteira. É a mesma disciplina da SIDRA — um
    dado ruim não pode derrubar a série toda (e `_com_retry` só pega erro de
    rede, não erro de conversão).
    """
    resposta = requests.get(URL_SGS.format(codigo=codigo), timeout=20)
    resposta.raise_for_status()
    bruto = resposta.json()[-ultimos:]
    pontos = []
    for p in bruto:
        try:
            data = datetime.strptime(p["data"], "%d/%m/%Y").date().isoformat()
            valor = float(str(p["valor"]).replace(",", "."))
        except (ValueError, TypeError, KeyError):
            continue
        pontos.append({"data": data, "valor": valor})
    return pontos


def _resolver_codigo(serie: str | int) -> int:
    """Aceita um atalho ('ipca') ou um código cru ('433' ou 433)."""
    if isinstance(serie, int):
        return serie
    chave = str(serie).strip().lower()
    if chave in ATALHOS:
        return ATALHOS[chave]
    if chave.isdigit():
        return int(chave)
    raise ValueError(
        f"não entendi a série '{serie}': use um atalho {list(ATALHOS)} "
        f"ou o código numérico da série no SGS"
    )


@tool
def coletar_serie_sgs(serie: str, ultimos: int = 12, nome: str = "") -> dict:
    """Coleta uma série temporal do Banco Central (sistema SGS).

    Aceita duas formas de pedir a série:
    - um ATALHO conhecido: 'ipca', 'selic', 'cambio', 'igpm';
    - o CÓDIGO numérico de qualquer série do SGS (ex.: '24364').

    Para um código fora dos atalhos, passe TAMBÉM o nome da série no argumento
    `nome` (ex.: serie='24364', nome='IBC-Br'). A API do BCB não devolve o
    nome, então sem ele não dá para confirmar que é a série certa — a tool vai
    recusar e pedir o nome. Se o usuário não souber o nome, peça a ele antes de
    chamar esta tool.

    `ultimos` é quantos pontos trazer. Devolve {serie_nome, codigo, pontos:
    [{data, valor}]}. Para indicadores do Banco Central (juros, câmbio,
    inflação como série de tempo). Para os GRUPOS do IPCA, use a tool da SIDRA.
    """
    codigo = _resolver_codigo(serie)
    nome_resolvido = resolver_nome(codigo, nome_usuario=nome.strip() or None)

    # GUARDRAIL: código que ninguém sabe nomear e sem nome do usuário.
    # Recusar é mais seguro que coletar números sem saber o que são.
    if nome_resolvido is None:
        raise ValueError(
            f"não sei o nome da série {codigo} (não está no catálogo nem no "
            f"portal de dados abertos). Peça ao usuário o nome dessa série e "
            f"passe-o no argumento `nome` para eu confirmar o que estou coletando."
        )

    try:
        pontos = _via_lib(codigo, ultimos)
        fonte = "python-bcb"
    except Exception as erro:
        # Erro recuperável: a lib falhou, mas a API direta pode responder.
        # Logamos o porquê — sem isso, "por que caiu no fallback?" vira
        # adivinhação na hora de depurar.
        log.info("python-bcb falhou para a série %s (%s); tentando a API HTTP",
                 codigo, erro)
        pontos = _com_retry(lambda: _via_http(codigo, ultimos))
        fonte = "api-http"

    log.info("série %s coletada via %s: %d pontos", codigo, fonte, len(pontos))
    return {"serie_nome": nome_resolvido, "codigo": codigo, "pontos": pontos}
