"""O agente REDATOR: busca o noticiário e escreve o contexto.

Terceiro nó do time. Ele recebe o bastão com as variações já calculadas, e
sua função é cercá-lo de contexto: o que a imprensa econômica anda dizendo
sobre o indicador. Tem uma tool só — a busca de notícias — e o resto do
trabalho é redação: resumir as manchetes em poucas frases.
"""

import json
import logging

from langchain_core.messages import ToolMessage

from agents.comum import carregar_prompt, rodar_agente
from state import State
from tools import TOOLS_REDATOR

log = logging.getLogger("time.redator")


def _ler_noticias(tool_messages: list[ToolMessage]) -> tuple[list, list]:
    """Recupera as manchetes e os avisos que a tool de notícias publicou.

    Devolve (noticias, avisos). O `aviso` (busca que falhou, total ou parcial)
    não pode ser descartado: sem ele, o revisor não distingue "não há notícias"
    de "a busca não respondeu" — e poderia tratar a ausência como se fosse fato.
    """
    for msg in tool_messages:
        try:
            c = json.loads(msg.content)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(c, dict) and "noticias" in c:
            avisos = [c["aviso"]] if c.get("aviso") else []
            return c["noticias"], avisos
    return [], []


def redator(state: State) -> dict:
    """Nó do grafo: busca notícias e publica o contexto no mural.

    Monta o pedido com o que o analista já apurou (indicador e variações), para
    o redator escrever um contexto que conversa com o número — não um resumo
    solto de notícias.
    """
    indicador = state["indicador"]
    variacoes = state.get("variacoes", {}).get("variacoes", {})

    resumo_num = ""
    if variacoes:
        mensal = variacoes.get("mensal")
        doze = variacoes.get("doze_meses")
        partes = []
        if mensal is not None:
            partes.append(f"{mensal}% no mês")
        if doze is not None:
            partes.append(f"{doze}% em 12 meses")
        if partes:
            resumo_num = f" As variações recentes são: {', '.join(partes)}."

    pedido = (
        f"O indicador em análise é '{indicador}'.{resumo_num} "
        f"Busque notícias recentes sobre ele e resuma o contexto."
    )
    log.info("redator começou (indicador=%s)", indicador)

    saida = rodar_agente(carregar_prompt("redator"), pedido, TOOLS_REDATOR, log)
    noticias, avisos = _ler_noticias(saida["tool_messages"])
    for aviso in avisos:
        log.warning("redator: %s", aviso)

    log.info("redator terminou: %d notícias, contexto com %d caracteres",
             len(noticias), len(saida["texto"]))

    return {
        "noticias": noticias,
        "contexto": saida["texto"],
        "avisos": avisos,   # propaga falha de busca ao mural (reducer acumula)
        "handoffs": ["redator → revisor"],
    }
