"""O agente VISUALIZADOR: transforma as variações num gráfico.

Segundo nó do time. Ele recebe do analista as séries de variação já calculadas
e tem uma única função: desenhar. Tem uma tool só — plotar_variacoes — e o nó
publica no mural o caminho do PNG gerado, para o revisor mencioná-lo no relatório.

É um agente deliberadamente estreito: separar "calcular" de "desenhar" mantém
cada peça simples e testável, e deixa claro no grafo quem produz o quê.
"""

import json
import logging

from langchain_core.messages import ToolMessage

from agents.comum import carregar_prompt, rodar_agente
from state import State
from tools import TOOLS_VISUALIZADOR

log = logging.getLogger("time.visualizador")


def _ler_graficos(tool_messages: list[ToolMessage]) -> tuple[list, list]:
    """Recupera os caminhos dos PNGs e eventuais erros das ToolMessages."""
    graficos, erros = [], []
    for msg in tool_messages:
        try:
            c = json.loads(msg.content)
        except (json.JSONDecodeError, TypeError):
            texto = str(getattr(msg, "content", "")).strip()
            if texto:
                erros.append(texto[:300])
            continue
        if isinstance(c, dict):
            if c.get("arquivo"):
                graficos.append(c["arquivo"])
            if c.get("erro"):
                erros.append(c["erro"])
    return graficos, erros


def visualizador(state: State) -> dict:
    """Nó do grafo: roda o agente visualizador e publica os gráficos no mural."""
    indicador = state["indicador"]
    variacoes = state.get("variacoes", {})
    log.info("visualizador começou (indicador=%s)", indicador)

    # Monta o pedido com os dados que o analista já apurou, para o visualizador
    # plotar exatamente o que está no mural (sem ir buscar nada de novo).
    pedido = (
        f"Plote as variações do indicador '{indicador}'. "
        f"Use serie_mensal e serie_interanual abaixo.\n"
        f"serie_mensal={json.dumps(variacoes.get('serie_mensal', []), ensure_ascii=False)}\n"
        f"serie_interanual={json.dumps(variacoes.get('serie_interanual', []), ensure_ascii=False)}"
    )
    saida = rodar_agente(carregar_prompt("visualizador"), pedido, TOOLS_VISUALIZADOR, log)
    graficos, erros = _ler_graficos(saida["tool_messages"])

    log.info("visualizador terminou: %d gráfico(s)", len(graficos))
    return {
        "graficos": graficos,
        "avisos": erros,
        "handoffs": ["visualizador → redator"],
    }
