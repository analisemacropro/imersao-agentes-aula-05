"""Tool de variações: transforma uma série em todas as leituras usuais.

Um número solto não diz muito. O que o economista lê é a VARIAÇÃO — e há vários
tipos, cada um respondendo uma pergunta diferente:

  - mensal (M/M-1):     acelerou ou desacelerou em relação ao mês passado?
  - interanual (M/M-12): como está contra o mesmo mês do ano anterior?
  - acumulada no ano:    quanto já variou de janeiro até aqui?
  - acumulada em 12m:    a leitura "anual" mais citada (12 meses móveis).
  - média móvel (MM3M):  suaviza o ruído mês a mês, mostra a tendência.
  - trimestral:          agrega a série mensal em trimestres e varia tri/tri.

Um cuidado decide a conta certa: a série é de NÍVEL (um número-índice, como a
PMC=105) ou já é uma TAXA em % (como o IPCA mensal=0,58%)? Para um índice, a
variação é (novo/antigo − 1)×100 e o acúmulo é o produto dos fatores. Para uma
série que já é variação %, somar não serve — o acúmulo também é por composição
de (1 + taxa/100). O parâmetro `ja_e_taxa` escolhe o caminho certo.
"""

from langchain_core.tools import tool


def _pct(novo: float, antigo: float) -> float | None:
    """Variação percentual de `antigo` para `novo`. None se não dá para calcular."""
    if antigo is None or novo is None or antigo == 0:
        return None
    return round((novo / antigo - 1) * 100, 3)


def _acumula_taxas(taxas: list[float]) -> float:
    """Compõe uma lista de variações % (ex.: [0.5, 0.3] -> 0.802), não soma.

    Inflação não se soma: 0,5% e depois 0,3% acumulam (1,005×1,003−1)=0,802%.
    """
    fator = 1.0
    for t in taxas:
        fator *= (1 + t / 100)
    return round((fator - 1) * 100, 3)


@tool
def calcular_variacoes(pontos: list[dict], ja_e_taxa: bool = False) -> dict:
    """Calcula as variações de uma série mensal: M/M, M/M-12, YTD, 12m, MM3M, tri.

    Recebe `pontos` ([{data, valor}], ordenados do mais antigo ao mais recente) e
    devolve as leituras usuais do último mês disponível, além das séries de
    variação mensal e interanual (para o visualizador plotar).

    Use `ja_e_taxa=True` quando os valores JÁ forem uma variação em % (ex.: IPCA
    mensal), para o acúmulo ser por composição, não por divisão de níveis. Para
    um número-índice (PMC, PIM, PMS), deixe `ja_e_taxa=False` (padrão).

    Devolve {ultimo, variacoes: {mensal, interanual, ano, doze_meses, mm3m,
    trimestral}, serie_mensal: [...], serie_interanual: [...]}.
    """
    pts = [p for p in pontos if p.get("valor") is not None]
    if len(pts) < 2:
        return {"erro": f"série curta demais para variações ({len(pts)} pontos)."}

    pts = sorted(pts, key=lambda p: p["data"])
    valores = [float(p["valor"]) for p in pts]
    datas = [p["data"] for p in pts]
    ultimo = {"data": datas[-1], "valor": valores[-1]}

    # --- Variação mensal (M/M-1) e interanual (M/M-12) ---
    if ja_e_taxa:
        # A série já é a própria variação mensal; M/M é o valor do mês.
        serie_mensal = [{"data": d, "valor": round(v, 3)} for d, v in zip(datas, valores)]
        # Interanual de uma série de taxas = acúmulo dos 12 meses que terminam ali.
        serie_interanual = []
        for i in range(11, len(valores)):
            serie_interanual.append({"data": datas[i],
                                     "valor": _acumula_taxas(valores[i - 11:i + 1])})
        var_mensal = round(valores[-1], 3)
    else:
        # Série de nível: M/M e M/M-12 são razões entre níveis.
        serie_mensal = [{"data": datas[i], "valor": _pct(valores[i], valores[i - 1])}
                        for i in range(1, len(valores))]
        serie_interanual = [{"data": datas[i], "valor": _pct(valores[i], valores[i - 12])}
                            for i in range(12, len(valores))]
        var_mensal = _pct(valores[-1], valores[-2])

    interanual = serie_interanual[-1]["valor"] if serie_interanual else None

    # --- Acumulada no ano (YTD): de janeiro até o último mês ---
    ano_atual = datas[-1][:4]
    meses_do_ano = [(d, v) for d, v in zip(datas, valores) if d[:4] == ano_atual]
    if ja_e_taxa:
        ano = _acumula_taxas([v for _, v in meses_do_ano])
    else:
        # Acumulado no ano de um índice: nível atual vs. nível de dez do ano
        # anterior (a base). Comparamos por ANO-MÊS (d[:7]), não pelo dia exato:
        # o SGS devolve a data com o dia real (não normalizado para 01), então
        # `d == "AAAA-12-01"` falharia justamente para câmbio/Selic. Se não há
        # dezembro anterior na janela, o YTD fica None (e avisamos abaixo).
        dez_anterior = f"{int(ano_atual)-1}-12"
        base = next((v for d, v in zip(datas, valores) if d[:7] == dez_anterior), None)
        ano = _pct(valores[-1], base) if base is not None else None

    # --- Acumulada em 12 meses móveis ---
    if ja_e_taxa:
        doze = _acumula_taxas(valores[-12:]) if len(valores) >= 12 else None
    else:
        doze = _pct(valores[-1], valores[-13]) if len(valores) >= 13 else None

    # --- Média móvel de 3 meses (MM3M) ---
    # É a MÉDIA dos 3 últimos valores, não a composição deles. Para uma série de
    # taxa (IPCA), a MM3M é a média das variações mensais — a leitura usual de
    # mercado para suavizar o ruído. (Compor os 3 meses daria o ACUMULADO no
    # trimestre, que é outra coisa: é o que a variação trimestral mede.)
    mm3m = round(sum(valores[-3:]) / 3, 3) if len(valores) >= 3 else None

    # --- Variação trimestral: agrega a série mensal em trimestres ---
    trimestral = _variacao_trimestral(datas, valores, ja_e_taxa)

    return {
        "ultimo": ultimo,
        "ja_e_taxa": ja_e_taxa,
        "variacoes": {
            "mensal": var_mensal,
            "interanual": interanual,
            "ano": ano,
            "doze_meses": doze,
            "mm3m": mm3m,
            "trimestral": trimestral,
        },
        "serie_mensal": serie_mensal,
        "serie_interanual": serie_interanual,
    }


def _variacao_trimestral(datas: list[str], valores: list[float], ja_e_taxa: bool):
    """Agrega a série mensal em trimestres e compara dois trimestres cheios.

    Mensal → trimestral depende do tipo da série, e a UNIDADE do resultado muda:

      - série de TAXA (ex.: IPCA): cada trimestre é o ACÚMULO dos seus 3 meses
        (composição). A leitura tri/tri é a ACELERAÇÃO entre os dois trimestres,
        em PONTOS PERCENTUAIS (ex.: 1,5% no T2 vs 1,2% no T1 → +0,3 p.p.).
        Compor (1,5/1,2) não teria sentido econômico ("inflação subiu 25%").
      - série de NÍVEL (ex.: câmbio): o nível trimestral é a MÉDIA dos 3 meses,
        e a variação tri/tri é percentual (%), como qualquer razão de níveis.

    Só entram trimestres com os 3 meses completos (não comparar tri pela metade).
    """
    trimestres: dict[str, list[float]] = {}
    for d, v in zip(datas, valores):
        ano, mes = int(d[:4]), int(d[5:7])
        chave = f"{ano}T{(mes - 1) // 3 + 1}"
        trimestres.setdefault(chave, []).append(v)

    # Só trimestres com os 3 meses completos entram (evita comparar tri pela metade).
    cheios = [(k, vs) for k, vs in sorted(trimestres.items()) if len(vs) == 3]
    if len(cheios) < 2:
        return None
    if ja_e_taxa:
        niveis = [_acumula_taxas(vs) for _, vs in cheios]  # variação do trimestre
        # variação tri/tri de taxas já acumuladas: diferença em p.p. é o usual aqui
        return round(niveis[-1] - niveis[-2], 3)
    niveis = [sum(vs) / 3 for _, vs in cheios]              # nível médio do trimestre
    return _pct(niveis[-1], niveis[-2])
