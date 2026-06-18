"""As ferramentas do time, agrupadas por quem as usa.

Na Aula 2 havia um agente só, com uma lista única de tools. Agora são vários
agentes, e cada um enxerga apenas as ferramentas do seu ofício — o analista não
busca notícias, o redator não calcula variações. Separar as listas é o primeiro
guardrail do time: um agente não chama o que não é dele.

  - TOOLS_ANALISTA    — coleta (BCB/IBGE) + cálculo das variações.
  - TOOLS_VISUALIZADOR — desenha as variações num gráfico.
  - TOOLS_REDATOR     — busca de notícias.
  - O revisor não tem tools: ele raciocina sobre o que já está no mural.
"""

from tools.bcb_sgs import coletar_serie_sgs
from tools.grafico import plotar_variacoes
from tools.ibge_catalogo import combinacao_sidra
from tools.ibge_sidra import coletar_sidra, descrever_tabela_sidra
from tools.noticias import buscar_noticias
from tools.schemas import PontoSerie, faltam_meses, valida_pontos
from tools.variacoes import calcular_variacoes

# O analista coleta e calcula as variações. `combinacao_sidra` entrega a
# combinação pronta dos indicadores de atividade (PMC/PIM/PMS), que exigem
# tabela+variável+classificação específicas e não dá para adivinhar.
TOOLS_ANALISTA = [
    coletar_serie_sgs,
    combinacao_sidra,
    coletar_sidra,
    descrever_tabela_sidra,
    calcular_variacoes,
]

# O visualizador só desenha — os números já estão no mural, postos pelo analista.
TOOLS_VISUALIZADOR = [plotar_variacoes]

# O redator só busca notícias — o contexto, não os números.
TOOLS_REDATOR = [buscar_noticias]

__all__ = [
    "TOOLS_ANALISTA",
    "TOOLS_VISUALIZADOR",
    "TOOLS_REDATOR",
    "coletar_serie_sgs",
    "combinacao_sidra",
    "coletar_sidra",
    "descrever_tabela_sidra",
    "calcular_variacoes",
    "plotar_variacoes",
    "buscar_noticias",
    "PontoSerie",
    "faltam_meses",
    "valida_pontos",
]
