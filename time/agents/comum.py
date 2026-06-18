"""O que os três agentes compartilham: o modelo e o mini-loop de tools.

Cada agente do time é, por dentro, o mesmo agente da Aula 2 — um modelo que
decide qual tool chamar, num loop, até parar. Em vez de repetir esse loop três
vezes (uma por agente), ele mora aqui, e cada agente só informa QUAIS tools tem
e QUAL prompt segue.

Manter o loop interno fora do grafo principal é uma decisão de desenho: o
vai-e-vem de cada agente com suas tools é "memória por agente", e não precisa
sujar o `State` global do time. O grafo da Aula 3 enxerga só o resultado limpo
que cada agente publica — não a conversa que ele teve para chegar lá.
"""

from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI

AQUI = Path(__file__).resolve().parent.parent
PROMPTS = AQUI / "prompts"

# Mesmo modelo da Aula 2: o Flash Lite, pequeno e barato (faixa grátis hoje).
# Num time real, cada papel poderia usar um modelo diferente — Haiku para
# validar, Opus para a redação difícil. Aqui usamos um só para focar no grafo.
MODELO = "gemini-flash-lite-latest"

# Trava de segurança do loop: nenhum agente chama tools mais que isto. Sem ela,
# um agente confuso poderia girar para sempre, queimando tokens.
MAX_VOLTAS = 6

_llm_cache: dict[tuple, object] = {}


def _modelo_com_tools(tools: tuple):
    """Cria (uma vez por conjunto de tools) o modelo com as ferramentas presas.

    Lazy de propósito: importar este módulo não deve exigir a chave de API. O
    modelo só nasce quando um agente roda de fato.
    """
    # As tools (StructuredTool) não são hasháveis, então a chave do cache é a
    # tupla dos NOMES — basta para distinguir o analista do redator.
    chave = tuple(t.name for t in tools)
    if chave not in _llm_cache:
        llm = ChatGoogleGenerativeAI(model=MODELO, temperature=0)
        _llm_cache[chave] = llm.bind_tools(list(tools)) if tools else llm
    return _llm_cache[chave]


def carregar_prompt(nome: str) -> str:
    """Lê o system prompt de um agente do arquivo prompts/<nome>.md."""
    return (PROMPTS / f"{nome}.md").read_text(encoding="utf-8")


def rodar_agente(prompt_sistema: str, pedido: str, tools: list, log=None) -> dict:
    """Roda o loop interno de um agente: modelo ⇄ tools, até ele parar.

    Devolve {texto, tool_messages}: a resposta final em texto e a lista de
    ToolMessages que as tools produziram no caminho (é de onde o nó do grafo
    extrai os dados estruturados — pontos, variações, notícias — para publicar
    no mural).
    """
    from langgraph.prebuilt import ToolNode

    nodo_tools = ToolNode(tools, handle_tool_errors=True) if tools else None
    modelo = _modelo_com_tools(tuple(tools))

    mensagens = [SystemMessage(prompt_sistema), HumanMessage(pedido)]
    tool_messages: list[ToolMessage] = []

    for _ in range(MAX_VOLTAS):
        resposta = modelo.invoke(mensagens)
        mensagens.append(resposta)
        if not getattr(resposta, "tool_calls", None):
            break  # o agente não pediu mais nada: terminou
        for tc in resposta.tool_calls:
            if log:
                log.info("  tool=%s args=%s", tc["name"], tc["args"])
        # O ToolNode executa todas as tools pedidas e devolve as ToolMessages.
        saida = nodo_tools.invoke({"messages": mensagens})
        novas = saida["messages"]
        mensagens.extend(novas)
        tool_messages.extend(m for m in novas if isinstance(m, ToolMessage))

    texto = _texto(mensagens[-1])
    return {"texto": texto, "tool_messages": tool_messages}


def _texto(mensagem) -> str:
    """Extrai o texto de uma resposta do Gemini (que vem em blocos)."""
    conteudo = getattr(mensagem, "content", "")
    if isinstance(conteudo, str):
        return conteudo
    # O Gemini devolve uma lista de blocos [{'type':'text','text':...}].
    partes = [b.get("text", "") for b in conteudo if isinstance(b, dict)]
    return "\n".join(p for p in partes if p).strip()
