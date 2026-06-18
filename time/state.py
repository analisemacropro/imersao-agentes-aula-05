"""O State do time — o quadro-negro que os agentes compartilham.

Na Aula 2 o State servia um agente só. Aqui ele vira o ponto de encontro de um
time: o analista escreve as variações, o visualizador escreve o gráfico, o
redator lê o número e escreve o contexto das notícias, o revisor lê tudo e
escreve o veredito. Cada nó lê o que precisa e acrescenta o seu — é o padrão
"blackboard", e no LangGraph o blackboard é exatamente este TypedDict.

Vale distinguir duas memórias que convivem aqui:

  - MEMÓRIA COMPARTILHADA — os campos estruturados abaixo (indicador, pontos,
    variacoes, graficos, noticias, revisao). É o que um agente precisa que o
    outro veja.
  - MEMÓRIA POR AGENTE — a conversa interna de cada agente com o modelo (os
    `messages` do seu loop de tools). Essa NÃO entra no mural global: fica no
    nó, é descartada quando ele termina, e só o resultado limpo é publicado.
    Manter o rascunho fora do mural evita poluir o contexto (e a conta de
    tokens) dos outros agentes com o vai-e-vem de cada um.
"""

import operator
from typing import Annotated, TypedDict


class State(TypedDict, total=False):
    # --- Entrada ---
    indicador: str        # o que estudar: 'ipca', 'pmc', 'selic'...
    pedido: str           # o pedido em linguagem natural (ex.: "analise o IPCA")

    # --- Memória compartilhada: o que cada agente publica para os outros ---
    pontos: list          # série coletada e validada [{data, valor}] (analista)
    variacoes: dict       # M/M, M/M-12, YTD, 12m, MM3M, tri + séries (analista)
    graficos: list        # caminhos dos PNGs gerados (visualizador)
    noticias: list        # manchetes recentes [{titulo, fonte, data, url}] (redator)
    contexto: str         # leitura do redator sobre o que as notícias dizem

    revisao: dict         # veredito do revisor: {ok, conflitos, observacoes}
    relatorio: str        # a resposta final, escrita pelo revisor

    # --- Trilha de execução: avisos e log de handoffs, para depurar o time ---
    # Os dois usam o reducer `operator.add`: cada nó ACRESCENTA à lista, em vez
    # de sobrescrever. Assim o mural acumula os avisos e os handoffs de todos os
    # agentes, na ordem em que rodaram — sem um nó apagar o rastro do anterior.
    avisos: Annotated[list, operator.add]      # tudo que mereceu um alerta
    handoffs: Annotated[list, operator.add]    # quem passou o bastão para quem
