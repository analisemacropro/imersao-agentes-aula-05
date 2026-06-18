"""A ponte entre o dashboard e o time multi-agente.

A Aula 4 pôs o time para rodar SOZINHO (boletim agendado). A Aula 5 faz o
contrário: o mesmo time responde SOB DEMANDA, a cada pergunta do usuário no
dashboard. O time é o mesmo da Aula 3 — não reescrevemos nada; vestimos o time
com uma interface nova.

Duas funções públicas:
  - responder(pedido): roda o time e vai EMITINDO o progresso (qual agente está
    trabalhando), terminando com o resultado estruturado. É um gerador, para o
    dashboard mostrar o time trabalhando em vez de uma tela congelada.
  - extrair(state): separa o State final do time nas peças que a tela exibe —
    tabela (a série), gráfico (PNG), variações (métricas), texto e notícias.

Por que `stream()` e não `rodar()`? O `rodar()` do time devolve tudo de uma vez,
no fim. Num chat, isso seria uma espera muda de vários segundos. O grafo do
LangGraph sabe transmitir cada passo conforme ele acontece (`app.stream`), e é
disso que o dashboard se alimenta para narrar o progresso ao vivo.
"""

import logging
import sys
from pathlib import Path

log = logging.getLogger("dashboard.runtime")

# A pasta do time, irmã do pacote `dashboard/`. Caminho a partir de __file__
# (não do diretório de trabalho) para o app rodar de qualquer lugar. Inserimos
# no sys.path para o time achar seus módulos (tools, state, agents) com os
# imports absolutos dele — mesmo padrão da ponte da Aula 4.
TIME = Path(__file__).resolve().parent.parent / "time"
if TIME.is_dir():
    sys.path.insert(0, str(TIME))
else:
    log.warning("pasta do time não encontrada em %s", TIME)

# Rótulo amigável de cada nó do grafo, para a narração de progresso na tela.
AGENTES = {
    "analista": "🧮 Analista — coletando a série e calculando as variações…",
    "visualizador": "📊 Visualizador — desenhando o gráfico…",
    "redator": "📰 Redator — buscando notícias e resumindo o contexto…",
    "revisor": "🔎 Revisor — conferindo e escrevendo a resposta…",
}


def responder(pedido: str):
    """Roda o time para um pedido, emitindo progresso e o resultado no fim.

    É um GERADOR. A cada passo do grafo, emite um dicionário:
      {"tipo": "progresso", "agente": <nó>, "rotulo": <texto amigável>}
    e, ao terminar, um único:
      {"tipo": "resultado", "state": <State final acumulado>}

    O State final é montado acumulando os updates do stream — cada nó devolve só
    o que mudou, e nós juntamos num mural só (os campos de lista do State, como
    `avisos` e `handoffs`, são estendidos; o resto é sobrescrito pelo mais novo).
    """
    from equipe import construir_grafo, _indicador_do_pedido

    app = construir_grafo()
    entrada = {"indicador": _indicador_do_pedido(pedido), "pedido": pedido,
               "avisos": [], "handoffs": []}

    state: dict = dict(entrada)
    # `stream_mode="updates"`: a cada passo o grafo emite {nó: update_parcial}.
    # É como sabemos QUAL agente acabou de rodar, para narrar na tela.
    for evento in app.stream(entrada, config={"recursion_limit": 16},
                             stream_mode="updates"):
        for no, update in evento.items():
            if no in AGENTES:
                yield {"tipo": "progresso", "agente": no, "rotulo": AGENTES[no]}
            _acumular(state, update)

    yield {"tipo": "resultado", "state": state}


def _acumular(state: dict, update: dict) -> None:
    """Funde o update parcial de um nó no mural acumulado.

    Listas com reducer no State do time (`avisos`, `handoffs`) são ESTENDIDAS,
    para o rastro não se perder; os demais campos o nó publica prontos, então
    o valor mais recente sobrescreve. Replica, no acúmulo manual, o que os
    reducers do LangGraph fariam — porque aqui montamos o State fora do grafo.
    """
    if not update:
        return
    for chave, valor in update.items():
        if chave in ("avisos", "handoffs") and isinstance(valor, list):
            state.setdefault(chave, []).extend(valor)
        else:
            state[chave] = valor


def extrair(state: dict) -> dict:
    """Separa o State final nas peças que o dashboard exibe.

    Cada campo do mural do time vira um elemento da interface:
      - pontos     -> tabela da série [{data, valor}]
      - graficos   -> caminho do PNG (a imagem)
      - variacoes  -> as leituras (M/M, 12m, no ano…) como métricas
      - relatorio  -> o texto final do revisor
      - noticias   -> as manchetes com link
      - avisos     -> o que mereceu alerta no caminho (transparência)
    Devolve um dicionário plano, pronto para a tela ler sem conhecer o time.
    """
    graficos = state.get("graficos") or []
    variacoes = state.get("variacoes") or {}
    return {
        "indicador": state.get("indicador", ""),
        "pontos": state.get("pontos") or [],
        "grafico": graficos[0] if graficos else None,
        "variacoes": variacoes.get("variacoes") or {},
        "relatorio": state.get("relatorio") or "",
        "contexto": state.get("contexto") or "",
        "noticias": state.get("noticias") or [],
        "avisos": state.get("avisos") or [],
        "handoffs": state.get("handoffs") or [],
    }
