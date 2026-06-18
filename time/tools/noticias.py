"""Tool de notícias: busca o noticiário recente sobre o indicador.

O analista trabalha com números; o redator precisa de contexto — o que a
imprensa econômica andou dizendo sobre o indicador. Esta tool faz uma busca de
notícias na web (via DuckDuckGo, que não pede chave de API) e devolve as
manchetes recentes.

Um detalhe que muda a qualidade da busca: o termo do indicador, sozinho, é
estreito. Quem pede a PMC quer saber de atividade econômica, não só do número
do comércio. Por isso a tool EXPANDE a palavra-chave para o tema ao redor —
PMC puxa "varejo" e "atividade econômica"; IPCA puxa "inflação". É a tradução
do indicador para o assunto que o leitor tem em mente.
"""

from langchain_core.tools import tool

# De indicador para o tema econômico ao redor. A primeira entrada é o próprio
# termo de busca; as demais alargam para o assunto. Editável à mão.
TEMAS = {
    "ipca": ["IPCA inflação Brasil"],
    "selic": ["Selic juros Copom Banco Central"],
    "cambio": ["dólar câmbio real Brasil"],
    "igpm": ["IGP-M inflação aluguel"],
    "pmc": ["PMC comércio varejo", "atividade econômica Brasil"],
    "pim": ["PIM produção industrial", "atividade econômica indústria"],
    "pms": ["PMS setor de serviços", "atividade econômica serviços"],
    "pib": ["PIB Brasil crescimento", "atividade econômica"],
}


def _consultas(indicador: str) -> list[str]:
    """Traduz o indicador na lista de buscas a fazer (com expansão de tema)."""
    chave = indicador.strip().lower()
    if chave in TEMAS:
        return TEMAS[chave]
    # Indicador fora do mapa: busca o termo cru, ainda assim funciona.
    return [f"{indicador} economia Brasil"]


@tool
def buscar_noticias(indicador: str, maximo: int = 5) -> dict:
    """Busca notícias recentes sobre um indicador econômico (e seu tema).

    Recebe o `indicador` (ex.: 'ipca', 'pmc', 'selic') e devolve manchetes
    recentes da imprensa. A busca expande o indicador para o assunto ao redor —
    pedir 'pmc' também traz notícias de atividade econômica, não só do número
    do comércio.

    Use para dar contexto ao relatório: o que o noticiário diz sobre o
    indicador agora. Devolve {consultas, noticias: [{titulo, fonte, data,
    url}]}. Se a busca falhar (rede fora), devolve a lista vazia com um aviso —
    não inventa manchetes.
    """
    from ddgs import DDGS

    encontradas: list[dict] = []
    consultas = _consultas(indicador)
    vistos = set()  # dedup por título, para as consultas não repetirem notícia
    falhas: list[str] = []  # consultas que caíram, para sinalizar falha PARCIAL

    # O try/except fica DENTRO do loop, por consulta: se a 1ª busca cai mas a 2ª
    # responde, ainda aproveitamos a 2ª e registramos só a falha da 1ª. Um
    # except em volta do loop inteiro perderia tudo por causa de uma consulta.
    with DDGS() as ddgs:
        for consulta in consultas:
            try:
                resultados = list(ddgs.news(consulta, region="br-pt", max_results=maximo))
            except Exception as erro:
                falhas.append(f"'{consulta}': {erro}")
                continue
            for r in resultados:
                titulo = (r.get("title") or "").strip()
                if not titulo or titulo in vistos:
                    continue
                vistos.add(titulo)
                encontradas.append({
                    "titulo": titulo,
                    "fonte": r.get("source") or "",
                    "data": (r.get("date") or "")[:10],
                    "url": r.get("url") or "",
                })

    # Ordena da mais recente para a mais antiga e corta no total pedido.
    encontradas.sort(key=lambda x: x["data"], reverse=True)
    saida = {"consultas": consultas, "noticias": encontradas[: maximo * len(consultas)]}
    # Sinaliza a falha (total ou parcial) para o redator distinguir "não há
    # notícias" de "a busca não respondeu" — são coisas diferentes no relatório.
    if falhas:
        saida["aviso"] = "busca de notícias falhou em " + "; ".join(falhas)
    return saida
