"""O dashboard interativo — o time multi-agente vestido de chatbot.

Roda com:  streamlit run dashboard/app.py

A ideia da aula: a Aula 4 entregou o time por e-mail, no automático; aqui ele
responde na tela, sob demanda. O usuário digita um pedido em linguagem natural
("mostra a inflação dos últimos 12 meses", "como está o câmbio?") e o dashboard
aciona o MESMO time da Aula 3, exibindo cada peça do resultado — a série em
tabela, o gráfico, as variações como métricas, o texto do revisor e as notícias
— em abas. Enquanto o time trabalha, a tela narra qual agente está rodando.

O Streamlit reexecuta este script inteiro a cada interação. Por isso o estado
da conversa vive em `st.session_state` (sobrevive entre reexecuções) e o
resultado de cada pedido é guardado em cache: pedir "IPCA" duas vezes não roda
o time duas vezes.
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# `streamlit run` executa este arquivo como script — o pacote `dashboard` não
# está no path por padrão. Pomos a RAIZ do projeto (pai de dashboard/) no
# sys.path para o import do runtime funcionar de qualquer diretório.
RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from dashboard.runtime import responder, extrair  # noqa: E402

st.set_page_config(page_title="Painel de Indicadores · Análise Macro",
                   page_icon="📊", layout="wide")


# ── CACHE: rodar o time é caro; não repetir o mesmo pedido ────────────────────
# `st.cache_data` guarda o resultado por argumento — repetir "IPCA" na sessão
# devolve o guardado em vez de rodar os quatro agentes de novo (economia de
# tokens e de espera). Quando o pedido JÁ está em cache, o Streamlit nem chama
# a função: por isso o progresso ao vivo (abaixo) só aparece na primeira vez.
@st.cache_data(show_spinner=False)
def _resposta(pedido: str, _caixa=None) -> dict:
    """Roda o time para o pedido e devolve o resultado extraído (cacheado).

    `_caixa` (um st.status) é só para narrar o progresso; o underscore no nome
    diz ao Streamlit para NÃO usá-lo como chave de cache (ele não é serializável
    e muda a cada run). A chave de cache é só o `pedido`.
    """
    state = None
    for evento in responder(pedido):
        if evento["tipo"] == "progresso" and _caixa is not None:
            _caixa.write(evento["rotulo"])
        elif evento["tipo"] == "resultado":
            state = evento["state"]
    return extrair(state or {})


def _rodar_com_progresso(pedido: str) -> dict:
    """Roda o time narrando o progresso. No cache hit, retorna sem narrar."""
    caixa = st.status("Acionando o time…", expanded=True)
    resultado = _resposta(pedido, _caixa=caixa)
    caixa.update(label="Time concluiu.", state="complete", expanded=False)
    return resultado


# ── AS PEÇAS DO RESULTADO, CADA UMA NUMA ABA ─────────────────────────────────
def _mostrar_resultado(r: dict) -> None:
    """Renderiza as peças do State do time em abas: texto, tabela, gráfico…"""
    if not r.get("pontos") and not r.get("relatorio"):
        st.warning("O time não conseguiu produzir um resultado para este pedido. "
                   "Veja os avisos abaixo.")
        for aviso in r.get("avisos", []):
            st.caption(f"⚠️ {aviso}")
        return

    # CASO ESPECIAL — SELIC: não há série de variações, e sim a meta do Copom.
    # Mostramos a meta vigente e a última decisão como métricas no topo (o
    # `delta` do st.metric vira a seta verde/vermelha da mudança em p.p.).
    meta = r.get("meta_selic") or {}
    if meta.get("meta_atual") is not None:
        mud = meta.get("mudanca") or {}
        c1, c2 = st.columns(2)
        c1.metric("Meta Selic", f"{meta['meta_atual']}% a.a.",
                  delta=(f"{mud['delta_pp']:+} p.p." if mud else None))
        if mud:
            c2.metric("Última decisão do Copom",
                      f"{mud['de']}% → {mud['para']}%", delta=f"em {mud['data']}",
                      delta_color="off")
    else:
        # Demais indicadores: as variações como métricas (a leitura rápida).
        variacoes = r.get("variacoes") or {}
        if variacoes:
            cols = st.columns(len(variacoes))
            for col, (nome, valor) in zip(cols, variacoes.items()):
                col.metric(nome, f"{valor:+.2f}%" if isinstance(valor, (int, float)) else valor)

    aba_texto, aba_tabela, aba_grafico, aba_noticias = st.tabs(
        ["📝 Análise", "🔢 Tabela", "📊 Gráfico", "📰 Notícias"])

    with aba_texto:
        st.markdown(r.get("relatorio") or "_(sem texto)_")

    with aba_tabela:
        pontos = r.get("pontos") or []
        # Na Selic não há série; a "tabela" é o histórico de decisões do Copom.
        historico = (r.get("meta_selic") or {}).get("historico") or []
        if pontos:
            df = pd.DataFrame(pontos)
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.download_button("Baixar CSV", df.to_csv(index=False).encode("utf-8"),
                               file_name=f"{r.get('indicador','serie')}.csv",
                               mime="text/csv")
        elif historico:
            st.caption("Últimas decisões do Copom (a meta a cada mudança):")
            df = pd.DataFrame(historico).rename(columns={"data": "data", "valor": "meta (% a.a.)"})
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("Sem série tabular para este pedido.")

    with aba_grafico:
        grafico = r.get("grafico")
        if grafico and Path(grafico).is_file():
            st.image(grafico, use_container_width=True)
        elif r.get("meta_selic", {}).get("meta_atual") is not None:
            st.info("A Selic é uma meta que muda em reunião do Copom — não há "
                    "série mensal para um gráfico de variações. Veja a meta e a "
                    "última decisão acima.")
        else:
            st.info("Sem gráfico para este pedido.")

    with aba_noticias:
        noticias = r.get("noticias") or []
        if noticias:
            for n in noticias:
                titulo, url = n.get("titulo", "(sem título)"), n.get("url", "")
                fonte, data = n.get("fonte", ""), n.get("data", "")
                st.markdown(f"- [{titulo}]({url})  \n  <small>{fonte} · {data}</small>",
                            unsafe_allow_html=True)
        else:
            st.info("Sem notícias para este pedido.")

    if r.get("avisos"):
        with st.expander(f"⚠️ Avisos do time ({len(r['avisos'])})"):
            for aviso in r["avisos"]:
                st.caption(aviso)


# ── A INTERFACE ──────────────────────────────────────────────────────────────
st.title("📊 Painel de Indicadores")
st.caption("Pergunte por um indicador em linguagem natural — o time de agentes "
           "coleta, analisa, desenha e resume para você.")

with st.sidebar:
    st.subheader("Como usar")
    st.write("Digite um pedido no campo abaixo. Exemplos:")
    for ex in ("Analise o IPCA", "Decisão do Copom (Selic)",
               "Como está o câmbio?", "Mostre a PMC"):
        st.code(ex, language=None)
    st.divider()
    st.caption("Como a resposta é montada")
    st.markdown(
        "Um time de agentes resolve o pedido em quatro etapas:\n\n"
        "1. 🧮 **Analista** — coleta a série oficial (BCB/IBGE) e calcula as "
        "variações (no mês, em 12 meses, no ano, média móvel).\n"
        "2. 📊 **Visualizador** — desenha o gráfico das variações.\n"
        "3. 📰 **Redator** — busca notícias recentes e resume o contexto.\n"
        "4. 🔎 **Revisor** — confere se os números e as notícias batem e "
        "escreve a leitura final.\n\n"
        "Você acompanha cada etapa acontecendo na tela, e o resultado chega "
        "repartido nas abas: análise, tabela, gráfico e notícias."
    )

# Histórico da conversa: cada turno guarda o pedido e o resultado extraído.
historico = st.session_state.setdefault("historico", [])
for turno in historico:
    with st.chat_message("user"):
        st.write(turno["pedido"])
    with st.chat_message("assistant"):
        _mostrar_resultado(turno["resultado"])

if pedido := st.chat_input("Ex.: mostre a inflação dos últimos 12 meses"):
    with st.chat_message("user"):
        st.write(pedido)
    with st.chat_message("assistant"):
        resultado = _rodar_com_progresso(pedido)
        _mostrar_resultado(resultado)
    historico.append({"pedido": pedido, "resultado": resultado})
