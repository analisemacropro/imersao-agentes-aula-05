"""O time de análise: analista → visualizador → redator → revisor, supervisionados.

Este é o primeiro TIME multi-agente da imersão. Na Aula 2 havia um agente só;
aqui quatro especialistas dividem o mesmo mural (o State) e um supervisor roteia
o trabalho. O grafo é o mesmo do hello-agent da Aula 1 — nós, arestas, um State
que circula — só que com mais nós e um deles no comando.

A diferença entre um time e um pipeline em linha reta está no supervisor. Um
pipeline sempre faz A → B → C. O supervisor OLHA o mural e DECIDE o próximo
passo: se o analista não conseguiu coletar nada, não adianta desenhar gráfico
nem buscar notícias — ele pula direto para o revisor relatar a falha. É a aresta
condicional que transforma a fila numa equipe que reage ao que aconteceu.

O arquivo se chama `equipe.py` (e não `time.py`) de propósito: `time` é um
módulo da biblioteca padrão do Python, e batizar o nosso assim quebraria
qualquer `import time`. Primeira regra de quem organiza um pacote: não dê a um
módulo seu o nome de um da stdlib.

Uso:
    python equipe.py "analise o IPCA"
    python equipe.py "calcule as variações da Selic"
"""

import logging
import sys

from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph

from agents.analista import analista
from agents.redator import redator
from agents.revisor import revisor
from agents.visualizador import visualizador
from state import State

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s · %(message)s")
log = logging.getLogger("time")


# ── O SUPERVISOR ─────────────────────────────────────────────────────────────
# Não é um nó que faz trabalho; é o roteador. Olha o que já está no mural e diz
# qual agente roda em seguida — ou que o trabalho acabou. Mantê-lo simples (uma
# função que devolve um nome) é o que torna o fluxo do time legível.
def supervisor(state: State) -> str:
    """Decide o próximo agente a partir do estado do mural.

    A ordem das checagens importa: a condição de PARADA vem primeiro. Se o
    revisor já escreveu o relatório, o trabalho acabou — não importa se a coleta
    tinha dado certo ou não. Pôr essa checagem por último era o que prendia o
    time num laço quando a coleta falhava (o revisor relatava a falha, mas o
    supervisor o chamava de novo, e de novo).
    """
    handoffs = state.get("handoffs", [])

    # 1) PARADA: o revisor já fechou? Então terminamos.
    if state.get("relatorio"):
        log.info("supervisor: relatório pronto -> FIM")
        return END

    tem_dados = bool(state.get("pontos")) and bool(state.get("variacoes", {}).get("variacoes"))
    # "Já rodou?" pelo PREFIXO do handoff, não pela string exata — o rótulo varia
    # (sucesso vs. falha), mas começa sempre com "nome ". O espaço no fim do
    # prefixo evita casar um nome que seja início de outro.
    rodou = lambda nome: any(h.startswith(nome + " ") for h in handoffs)

    # 2) Início: ninguém analisou ainda — começa pelo analista.
    if not rodou("analista"):
        log.info("supervisor: começo -> analista")
        return "analista"

    # 3) Análise falhou (analista rodou, mas não há dados/variações): pula o
    #    visualizador e o redator e manda o revisor relatar a falha honestamente.
    if not tem_dados:
        log.info("supervisor: análise falhou -> pula para o revisor")
        return "revisor"

    # 4) Há variações, mas ainda não foram desenhadas? É a vez do visualizador.
    if not rodou("visualizador"):
        log.info("supervisor: variações prontas -> visualizador (gráfico)")
        return "visualizador"

    # 5) Gráfico pronto, mas falta o contexto das notícias? É a vez do redator.
    if not rodou("redator"):
        log.info("supervisor: gráfico pronto -> redator (contexto)")
        return "redator"

    # 6) Tudo pronto: revisor fecha.
    log.info("supervisor: contexto pronto -> revisor (fechamento)")
    return "revisor"


def construir_grafo(checkpointer=None):
    """Monta o grafo do time e devolve compilado.

    O desenho é em estrela: cada agente, ao terminar, volta para o supervisor,
    que decide o próximo. É o padrão SUPERVISOR — um coordenador central com
    visão do todo, em vez de cada agente chamar o próximo diretamente.
    """
    grafo = StateGraph(State)
    grafo.add_node("analista", analista)
    grafo.add_node("visualizador", visualizador)
    grafo.add_node("redator", redator)
    grafo.add_node("revisor", revisor)

    # O supervisor não é um nó: é a função de roteamento das arestas. Começamos
    # nele (via START) e cada agente volta a ele para a próxima decisão.
    rotas = {"analista": "analista", "visualizador": "visualizador",
             "redator": "redator", "revisor": "revisor", END: END}
    grafo.add_conditional_edges(START, supervisor, rotas)
    for agente in ("analista", "visualizador", "redator", "revisor"):
        grafo.add_conditional_edges(agente, supervisor, rotas)

    return grafo.compile(checkpointer=checkpointer)


def _indicador_do_pedido(pedido: str) -> str:
    """Descobre o indicador pela palavra-chave do pedido (como na Aula 2)."""
    p = pedido.lower()
    for nome in ("ipca", "selic", "cambio", "câmbio", "igpm", "pmc", "pim", "pms", "pib"):
        if nome in p:
            return "cambio" if nome == "câmbio" else nome
    return "ipca"


def rodar(pedido: str) -> State:
    """Roda o time inteiro para um pedido e devolve o mural final."""
    indicador = _indicador_do_pedido(pedido)
    app = construir_grafo()
    return app.invoke(
        {"indicador": indicador, "pedido": pedido, "avisos": [], "handoffs": []},
        # O limite de passos protege o time de um loop de supervisor mal-ajustado.
        # São 4 agentes, cada um com ida-e-volta ao supervisor; 16 dá folga.
        config={"recursion_limit": 16},
    )


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    pedido = args[0] if args else "analise o IPCA"

    estado = rodar(pedido)

    print("\n" + "=" * 64)
    print(estado.get("relatorio", "(sem relatório)"))
    print("=" * 64)
    print("\nHandoffs:", " | ".join(estado.get("handoffs", [])))
    revisao = estado.get("revisao", {})
    if revisao.get("conflitos"):
        print(f"Conflitos sinalizados: {len(revisao['conflitos'])}")
    if estado.get("avisos"):
        print(f"Avisos ({len(estado['avisos'])}):")
        for aviso in estado["avisos"]:
            print(f"  · {aviso}")


if __name__ == "__main__":
    main()
