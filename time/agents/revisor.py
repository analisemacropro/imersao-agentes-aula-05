"""O agente REVISOR: confere as peças, acha conflito e escreve o relatório.

Último nó do time, e o controle de qualidade. Diferente dos outros, ele não tem
tools — todo o material já está no mural (a série, as variações, o gráfico, as
notícias). Seu trabalho é cruzar essas peças e decidir se contam a mesma história.

A detecção de conflito é feita em DUAS camadas, na mesma filosofia da validação
da Aula 2:

  - no CÓDIGO, uma checagem barata e determinística: a variação mensal aponta um
    lado e a de 12 meses aponta o outro? Isso o código sabe medir sozinho.
  - no MODELO, o julgamento que a regra não cobre: as variações batem com o que
    as notícias dizem? Para isso é preciso ler as manchetes, e quem lê é a LLM.

O conflito que o código achar entra no prompt do revisor como um aviso, para
ele não deixar passar — e o relatório final registra a divergência em vez de
escondê-la.
"""

import logging

from agents.comum import carregar_prompt, rodar_agente
from state import State

log = logging.getLogger("time.revisor")


def _conflito_mensal_vs_anual(variacoes: dict) -> str | None:
    """Camada 1 (código): a leitura de curto prazo contradiz a de 12 meses?

    Quando a variação mensal vai num sentido e a acumulada em 12 meses vai no
    oposto, há uma virada de tendência que vale sinalizar — pode ser inflexão
    real ou ruído de um mês. Limiar pequeno para não disparar à toa.
    """
    v = variacoes.get("variacoes", {})
    mensal, doze = v.get("mensal"), v.get("doze_meses")
    if mensal is None or doze is None:
        return None
    if abs(mensal) < 0.05 or abs(doze) < 0.05:
        return None
    if (mensal > 0) != (doze > 0):
        dir_m = "alta" if mensal > 0 else "queda"
        dir_a = "alta" if doze > 0 else "queda"
        return (
            f"o mês aponta {dir_m} ({mensal:+.2f}%), mas o acumulado em 12 meses "
            f"aponta {dir_a} ({doze:+.2f}%). Pode ser inflexão ou ruído — "
            f"confirme antes de afirmar tendência."
        )
    return None


def _montar_briefing(state: State, conflito_codigo: str | None,
                     nota_checagem: str | None = None) -> str:
    """Reúne tudo o que o revisor precisa ler, num único texto de entrada."""
    indicador = state["indicador"]
    pontos = state.get("pontos", [])
    variacoes = state.get("variacoes", {})
    graficos = state.get("graficos", [])
    noticias = state.get("noticias", [])
    contexto = state.get("contexto", "")

    ult = pontos[-1] if pontos else {}
    linhas = [f"INDICADOR: {indicador}"]
    if ult:
        linhas.append(f"ÚLTIMO DADO: {ult.get('valor')} em {ult.get('data')} "
                      f"({len(pontos)} pontos coletados)")
    v = variacoes.get("variacoes", {})
    if v:
        # Lista só as variações que de fato foram calculadas (algumas vêm None).
        nomes = {"mensal": "mensal", "interanual": "interanual",
                 "ano": "no ano", "doze_meses": "12 meses",
                 "mm3m": "média móvel 3m", "trimestral": "trimestral"}
        # A trimestral de uma série de TAXA é aceleração em p.p., não %; o resto
        # é %. Marcar a unidade certa evita o revisor reportar p.p. como %.
        taxa = variacoes.get("ja_e_taxa")
        def _unid(k):
            return " p.p." if (k == "trimestral" and taxa) else "%"
        itens = [f"{nomes[k]}: {v[k]}{_unid(k)}" for k in nomes if v.get(k) is not None]
        if itens:
            linhas.append("VARIAÇÕES: " + "; ".join(itens))
    if graficos:
        linhas.append("GRÁFICO: " + "; ".join(graficos))
    if contexto:
        linhas.append(f"CONTEXTO DO REDATOR: {contexto}")
    if noticias:
        manchetes = "\n".join(f"  - {n['titulo']} ({n['fonte']}, {n['data']})"
                              for n in noticias[:6])
        linhas.append(f"NOTÍCIAS:\n{manchetes}")
    else:
        # Sem notícias: distinguir "não há" de "a busca falhou". Se o redator
        # propagou um aviso de busca para o mural, mostramos — o revisor então
        # diz "a busca não respondeu", em vez de tratar a ausência como fato.
        falha_busca = [a for a in state.get("avisos", []) if "notícia" in str(a).lower()]
        if falha_busca:
            linhas.append("NOTÍCIAS: " + "; ".join(falha_busca))
        else:
            linhas.append("NOTÍCIAS: nenhuma encontrada para o período.")
    if conflito_codigo:
        linhas.append(f"⚠️ ALERTA AUTOMÁTICO (verificado no código): {conflito_codigo}")
    if nota_checagem:
        linhas.append(f"NOTA: {nota_checagem}")

    linhas.append("\nConfira as peças, registre qualquer conflito e escreva o "
                  "relatório final conforme suas instruções.")
    return "\n".join(linhas)


def _relatorio_de_falha(state: State) -> str:
    """Relatório honesto quando falta uma peça essencial para revisar.

    Sem isto, o revisor receberia um briefing incompleto e o modelo, na falta
    de números, INVENTARIA um relatório plausível. A regra de ouro do projeto é
    não preencher buraco com ficção: se a coleta ou o cálculo falhou, o time DIZ
    que falhou, em vez de fingir um resultado. Por ser crítico, escrevemos esse
    texto no código — não delegamos ao modelo a decisão de inventar ou não.
    """
    indicador = state.get("indicador", "o indicador pedido")
    pontos = state.get("pontos", [])
    avisos = state.get("avisos", [])

    # `pontos` aqui já passou pela validação do analista; se está vazio, ou a
    # coleta não trouxe nada, ou nada passou na validação. Em ambos não há série.
    if not pontos:
        falta = ("a coleta não trouxe dados válidos (a fonte não respondeu, ou "
                 "os valores não passaram na validação) — não há série para analisar")
    else:
        falta = (f"a série foi coletada ({len(pontos)} pontos), mas as variações "
                 f"não foram calculadas (série curta demais)")
    motivo = "; ".join(str(a) for a in avisos) if avisos else "sem detalhe adicional."
    return (
        f"⚠️ Não foi possível concluir a análise de '{indicador}': {falta}.\n\n"
        f"Motivo: {motivo}\n\n"
        f"Nenhum número foi estimado — o time não inventa dados. "
        f"Verifique o código/combinação da fonte (no IBGE, use "
        f"descrever_tabela_sidra para achar a tabela e a variável certas; no "
        f"Banco Central, confirme o código da série) ou colete mais histórico, "
        f"e rode novamente."
    )


def revisor(state: State) -> dict:
    """Nó do grafo: checa conflito, escreve o relatório e fecha o time."""
    log.info("revisor começou")
    pontos = state.get("pontos", [])
    variacoes = state.get("variacoes", {})
    tem_variacoes = bool(variacoes.get("variacoes"))

    # PEÇA FALTANDO: caminho de falha. Não chamamos o modelo para "escrever um
    # relatório" sem o material — ele preencheria o buraco com números
    # inventados. Emitimos um relatório de falha honesto, escrito no código.
    # A condição é OU: basta faltar a série OU as variações.
    if not pontos or not tem_variacoes:
        log.warning("revisor: falta dado essencial (pontos=%d, variações=%s) "
                    "-> relatório de falha honesto", len(pontos), tem_variacoes)
        return {
            "revisao": {"ok": False, "conflitos": ["coleta/variações incompletas"]},
            "relatorio": _relatorio_de_falha(state),
            "handoffs": ["revisor → FIM"],
        }

    # Camada 1 — conflito que o código mede sozinho (mensal vs. 12 meses).
    conflito_codigo = _conflito_mensal_vs_anual(variacoes)
    if conflito_codigo:
        log.warning("conflito (código): %s", conflito_codigo)

    # Se faltou uma das pernas da comparação (série curta sem 12 meses, ex.:
    # câmbio recém-coletado), avisamos que a checagem NÃO pôde rodar — para o
    # revisor não tratar "não verifiquei" como "está tudo certo". O aviso entra
    # no briefing (não muta o State; o reducer do grafo cuida da persistência).
    v = variacoes.get("variacoes", {})
    nota_checagem = None
    if v.get("mensal") is None or v.get("doze_meses") is None:
        nota_checagem = ("a comparação mensal vs. 12 meses não foi possível "
                         "(série curta — faltou a mensal ou a de 12 meses).")

    # Camada 2 — o revisor lê tudo (inclusive o alerta acima) e julga o resto,
    # inclusive variações vs. notícias, e escreve o relatório.
    briefing = _montar_briefing(state, conflito_codigo, nota_checagem)
    saida = rodar_agente(carregar_prompt("revisor"), briefing, tools=[], log=log)
    relatorio = saida["texto"]

    # Registra os conflitos das duas camadas: o que o código mediu e o que o
    # revisor sinalizou no texto (marca "⚠️ Divergência"). Sem juntar os dois, o
    # mural diria "0 conflitos" mesmo quando o relatório aponta uma divergência.
    conflitos = [conflito_codigo] if conflito_codigo else []
    if "divergência" in relatorio.lower() and not conflito_codigo:
        conflitos.append("o revisor apontou divergência entre as variações e o "
                         "contexto das notícias (ver relatório)")
    revisao = {"ok": not conflitos, "conflitos": conflitos}
    log.info("revisor terminou: ok=%s, conflitos=%d", revisao["ok"], len(conflitos))

    return {"revisao": revisao, "relatorio": relatorio, "handoffs": ["revisor → FIM"]}
