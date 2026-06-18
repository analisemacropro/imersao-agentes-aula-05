"""O agente ANALISTA: coleta → valida → calcula as variações.

É o primeiro nó do time e o mais parecido com o agente da Aula 2 — reusa as
mesmas tools de coleta. A novidade é a tool de variações: depois de coletar a
série, ele calcula as leituras usuais (mensal, interanual, acumulada no ano e em
12 meses, média móvel, trimestral). O modelo decide a ordem das chamadas lendo
o prompt; o código aqui valida o que voltou e publica no mural.
"""

import json
import logging

from langchain_core.messages import ToolMessage

from agents.comum import carregar_prompt, rodar_agente
from state import State
from tools import TOOLS_ANALISTA, valida_pontos
from tools.schemas import JA_E_TAXA

log = logging.getLogger("time.analista")


def _ler_tools(tool_messages: list[ToolMessage]) -> dict:
    """Vasculha as ToolMessages e separa o que cada tool devolveu.

    Cada tool publica um JSON diferente; reconhecemos pelo formato: a coleta traz
    'pontos', o cálculo de variações traz 'variacoes'.
    """
    achado = {"pontos": [], "nome": "", "variacoes": {}, "erros": []}
    for msg in tool_messages:
        try:
            c = json.loads(msg.content)
        except (json.JSONDecodeError, TypeError):
            # Não era JSON: quando uma tool levanta erro, o ToolNode devolve a
            # MENSAGEM do erro como texto. Guardamos como aviso — é o que explica
            # POR QUE a coleta/cálculo falhou, em vez de sumir.
            texto = str(getattr(msg, "content", "")).strip()
            if texto:
                achado["erros"].append(texto[:300])
            continue
        if not isinstance(c, dict):
            continue
        if "erro" in c:
            achado["erros"].append(c["erro"])
        if c.get("aviso"):  # ex.: combinacao_sidra para indicador desconhecido
            achado["erros"].append(c["aviso"])
        if "pontos" in c:  # veio da coleta (BCB ou IBGE)
            achado["pontos"] = c["pontos"]
            achado["nome"] = c.get("serie_nome") or c.get("tabela_nome") or achado["nome"]
        if "variacoes" in c:  # veio do cálculo de variações
            achado["variacoes"] = c
    return achado


def analista(state: State) -> dict:
    """Nó do grafo: roda o agente analista e publica no mural.

    Recebe o indicador/pedido do State, roda o loop interno (coleta + cálculo),
    valida os pontos coletados com o schema da Aula 2 e devolve os campos que os
    colegas vão ler: `pontos` e `variacoes`.
    """
    indicador = state["indicador"]
    pedido = state.get("pedido") or f"Analise o indicador '{indicador}'."
    log.info("analista começou (indicador=%s)", indicador)

    saida = rodar_agente(carregar_prompt("analista"), pedido, TOOLS_ANALISTA, log)
    achado = _ler_tools(saida["tool_messages"])

    # Validação no CÓDIGO (camada 1 da Aula 2): as variações só valem o que
    # valem os dados que entraram, então conferimos os pontos antes de seguir.
    validados, avisos = valida_pontos(achado["pontos"], indicador)
    pontos_limpos = [{"data": p.data.isoformat(), "valor": p.valor} for p in validados]
    avisos.extend(achado["erros"])

    variacoes = achado["variacoes"]

    # DEFESA DE CÓDIGO para a escolha de `ja_e_taxa`. O modelo decide se a série
    # é taxa ou nível (pelo prompt), mas a escolha errada estraga TODAS as
    # variações em silêncio (IPCA tratado como nível vira número absurdo). Para
    # os indicadores que conhecemos, conferimos a escolha contra a verdade; em
    # divergência, DESCARTAMOS as variações erradas e sinalizamos — melhor
    # recusar do que publicar números computados errado.
    esperado = JA_E_TAXA.get(indicador)
    if variacoes and esperado is not None and variacoes.get("ja_e_taxa") != esperado:
        avisos.append(
            f"o modelo tratou '{indicador}' como "
            f"{'taxa' if variacoes.get('ja_e_taxa') else 'nível'}, mas é "
            f"{'taxa' if esperado else 'nível'} — as variações sairiam erradas; "
            f"descartadas. (Ajuste o pedido ou o prompt do analista.)"
        )
        variacoes = {}

    tem_variacoes = bool(variacoes.get("variacoes"))
    log.info("analista terminou: %d pontos, variações=%s", len(pontos_limpos), tem_variacoes)

    # O handoff reflete o que de fato aconteceu: sem variações, o trabalho não
    # chega pronto ao próximo. Assim o rastro do mural não mente.
    handoff = ("analista → visualizador" if tem_variacoes
               else "analista → (falha: sem variações)")

    return {
        "pontos": pontos_limpos,
        "variacoes": variacoes,
        "avisos": avisos,
        "handoffs": [handoff],
    }
