"""Contratos tipados com Pydantic — a primeira camada de validação.

Em vez de uma tool devolver um dicionário solto, validamos cada ponto contra
um schema. Se a API mandar texto onde devia vir número, ou uma data
impossível, o Pydantic reclama na hora, em vez de o erro aparecer três passos
depois, disfarçado no relatório.

A faixa de valor plausível depende do indicador: o IPCA mensal fica perto de
zero, a Selic perto de 15% a.a., o câmbio perto de 5 R$. Por isso a faixa é um
parâmetro, não um número cravado.
"""

from datetime import date

from pydantic import BaseModel, field_validator

# Faixas plausíveis por indicador (mín, máx). Um valor fora daqui é quase
# sempre erro de coleta — escala trocada, vírgula no lugar errado, campo vazio.
# São regras que você, como economista, sabe de cor.
FAIXAS = {
    "ipca": (-2.0, 5.0),      # variação mensal (%)
    "selic": (0.0, 50.0),     # meta anual (% a.a.)
    "cambio": (0.5, 15.0),    # R$/US$
    # Indicadores de atividade, em variação mensal (%) — oscilam mais que o
    # IPCA, então a faixa é mais larga; ainda assim pega erro grosseiro de escala.
    "pmc": (-20.0, 20.0),     # comércio varejo (variação mensal, %)
    "pim": (-30.0, 30.0),     # produção industrial (variação mensal, %)
    "pms": (-20.0, 20.0),     # serviços (variação mensal, %)
}

# A série já é uma TAXA em % (e o acúmulo é por composição), ou é um NÍVEL
# (e a variação é razão entre níveis)? Quem escolhe isso na hora de calcular é
# o modelo (pelo prompt do analista), mas a escolha errada estraga TODAS as
# variações em silêncio. Este mapa é a defesa no código: para os indicadores
# que a imersão conhece, conferimos a escolha do modelo contra a verdade.
#   - IPCA, IGP-M, PMC/PIM/PMS (variação m/m): já são taxa -> True
#   - câmbio, Selic: são nível (R$, % a.a.) -> False
JA_E_TAXA = {
    "ipca": True, "igpm": True, "pmc": True, "pim": True, "pms": True,
    "selic": False, "cambio": False,
}


class PontoSerie(BaseModel):
    """Um ponto de uma série temporal: uma data e um valor."""

    data: date
    valor: float


def valida_pontos(dados: list[dict], indicador: str) -> tuple[list[PontoSerie], list[str]]:
    """Camada 1 (schema) — converte cada ponto e separa o que não passa.

    Devolve (validados, avisos): os pontos que viraram `PontoSerie` sem erro
    e a lista de mensagens dos que foram descartados, com o porquê.
    """
    chave = indicador.strip().lower()
    validados, avisos = [], []
    if chave in FAIXAS:
        minimo, maximo = FAIXAS[chave]
    else:
        # Sem faixa cadastrada, a checagem de plausibilidade não roda — um
        # outlier grosseiro (ex.: 999999 de erro de coleta) passaria. Avisamos
        # para que isso não fique invisível e a faixa possa ser adicionada.
        minimo, maximo = float("-inf"), float("inf")
        avisos.append(f"sem faixa plausível para '{indicador}': "
                      f"a checagem de valor não foi aplicada")
    for ponto in dados:
        try:
            p = PontoSerie(**ponto)
        except Exception as erro:
            avisos.append(f"ponto descartado (forma inválida): {erro}")
            continue
        if not minimo <= p.valor <= maximo:
            avisos.append(
                f"ponto descartado ({p.data}): valor {p.valor} fora da "
                f"faixa plausível de '{indicador}' [{minimo}, {maximo}]"
            )
            continue
        validados.append(p)

    # Data repetida geraria uma variação mensal falsa de 0% (mesmo mês contra si).
    # Descartamos a duplicata, mantendo o primeiro ponto de cada data.
    sem_dup, vistas = [], set()
    for p in validados:
        if p.data in vistas:
            avisos.append(f"ponto descartado (data repetida): {p.data}")
            continue
        vistas.add(p.data)
        sem_dup.append(p)
    return sem_dup, avisos


def faltam_meses(serie: list[PontoSerie], esperados: int) -> bool:
    """Camada 2 (regra de domínio) — a série veio completa?

    O schema garante a forma de cada ponto; esta regra confere o conjunto.
    """
    return len(serie) < esperados
