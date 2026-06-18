"""Catálogo curado de combinações da SIDRA para os indicadores da imersão.

O IBGE não é como o Banco Central: uma série da SIDRA não é um código só, é uma
COMBINAÇÃO de tabela + variável + (às vezes) classificação + categoria. Pior:
algumas tabelas EXIGEM a classificação. A PMC (tabela 8880), por exemplo, só
devolve números se você disser o "tipo de índice" (volume, não receita) — sem
isso, vem vazio. Um agente que tenta adivinhar essa combinação erra, e a coleta
volta sem dados.

A defesa é a mesma do catálogo do BCB: um mapa curado, conferido à mão contra os
metadados, das combinações que a imersão usa. Cada entrada foi validada com uma
coleta real. Assim o analista pede o indicador pelo nome ('pmc') e recebe a
combinação certa, em vez de chutar tabela e variável.

(Para um indicador FORA deste mapa, o caminho continua sendo o da Aula 2: chamar
descrever_tabela_sidra, ler o cardápio e montar a combinação à mão.)
"""

from langchain_core.tools import tool

# Combinações conferidas contra os metadados e testadas com coleta real.
# Todas em variação mês/mês (% — a mesma unidade do IPCA mensal), que é o que
# faz sentido modelar e comparar. A categoria é obrigatória nessas tabelas.
CATALOGO_SIDRA = {
    "pmc": {
        "indicador": "PMC — volume de vendas no varejo (variação mensal, %)",
        "tabela": "8880", "variavel": "11708",      # variação m/m imediatamente anterior
        "classificacao": "11046", "categoria": "56734",  # tipo de índice: volume
    },
    "pim": {
        "indicador": "PIM — produção física industrial (variação mensal, %)",
        "tabela": "8888", "variavel": "11601",      # variação m/m
        "classificacao": "544", "categoria": "129314",   # indústria geral
    },
    "pms": {
        "indicador": "PMS — volume de serviços (variação mensal, %)",
        "tabela": "8688", "variavel": "11623",      # variação m/m
        "classificacao": "11046", "categoria": "56726",  # tipo de índice: volume
    },
}


@tool
def combinacao_sidra(indicador: str) -> dict:
    """Devolve a combinação SIDRA pronta de um indicador de atividade conhecido.

    Para indicadores do IBGE que exigem uma combinação específica de tabela +
    variável + classificação + categoria — PMC (varejo), PIM (indústria), PMS
    (serviços) —, esta tool entrega os códigos certos, já conferidos. Use-a
    ANTES de coletar esses indicadores: pegue a combinação aqui e passe-a para
    coletar_sidra.

    Recebe o nome do indicador ('pmc', 'pim', 'pms'). Devolve {indicador,
    tabela, variavel, classificacao, categoria}. Se o indicador não estiver no
    catálogo, devolve um aviso — aí use descrever_tabela_sidra para montar a
    combinação à mão.
    """
    chave = indicador.strip().lower()
    if chave in CATALOGO_SIDRA:
        return dict(CATALOGO_SIDRA[chave])
    return {
        "aviso": f"'{indicador}' não está no catálogo SIDRA (tenho: "
                 f"{list(CATALOGO_SIDRA)}). Use descrever_tabela_sidra para "
                 f"descobrir a tabela e a combinação certas."
    }
