"""Tool de gráfico: desenha as variações da série num PNG.

Variação em tabela é difícil de ler; um gráfico mostra a história de um relance.
Esta tool desenha duas leituras lado a lado: as variações MENSAIS em barras (o
ritmo mês a mês, verde quando sobe, vermelho quando cai) e a acumulada em 12
MESES em linha (a tendência). É o painel que o redator e o leitor de fato olham.

Roda em modo headless (backend 'Agg'): nenhuma janela abre, o que é o certo
para um agente que pode rodar num servidor sem tela. O retorno é o caminho do
arquivo, para o estado do time saber onde a figura ficou.
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # backend sem tela: salva em arquivo, não abre janela
import matplotlib.pyplot as plt  # noqa: E402  (o use('Agg') precisa vir antes)
from langchain_core.tools import tool

# Paleta da marca, a mesma dos diagramas do guia — para a figura combinar.
AZUL = "#282f6b"
VERDE = "#059669"
VERMELHO = "#dc2626"

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _so_validos(serie: list[dict]) -> tuple[list[str], list[float]]:
    """Separa (rótulos, valores) descartando pontos sem valor numérico."""
    datas, valores = [], []
    for p in serie:
        v = p.get("valor")
        if v is None:
            continue
        datas.append(str(p.get("data", ""))[:7])  # "AAAA-MM"
        valores.append(float(v))
    return datas, valores


@tool
def plotar_variacoes(serie_mensal: list[dict], serie_interanual: list[dict],
                     indicador: str = "serie", titulo: str = "") -> dict:
    """Plota as variações (mensal em barras + 12 meses em linha) e salva num PNG.

    Recebe as séries que o analista calculou: `serie_mensal` (variação M/M-1) e
    `serie_interanual` (variação acumulada em 12 meses), cada uma [{data, valor}].
    Desenha um painel com duas faixas e salva em data/variacoes_<indicador>.png.

    Use depois de calcular as variações, para gerar a figura do relatório.
    Devolve {arquivo, n_mensal, n_interanual}.
    """
    dm, vm = _so_validos(serie_mensal)
    di, vi = _so_validos(serie_interanual)
    if not vm and not vi:
        return {"erro": "sem variações válidas para plotar."}

    # Um painel por série que de fato tem dados — assim não sobra um quadro em
    # branco quando só uma das duas existe (ex.: série curta sem 12 meses).
    paineis = [p for p in ("mensal", "doze") if (p == "mensal" and vm) or (p == "doze" and vi)]

    # Todo o desenho + gravação fica num try/finally: qualquer erro no caminho
    # (bar, plot, savefig...) ainda fecha a figura, em vez de vazá-la na memória.
    fig, eixos = plt.subplots(len(paineis), 1, figsize=(9, 3 * len(paineis)), squeeze=False)
    try:
        eixo = {nome: eixos[i][0] for i, nome in enumerate(paineis)}
        if vm:
            cores = [VERDE if x >= 0 else VERMELHO for x in vm]
            eixo["mensal"].bar(range(len(vm)), vm, color=cores)
            eixo["mensal"].axhline(0, color="#64748b", linewidth=0.8)
            eixo["mensal"].set_title("Variação mensal (%)", fontsize=10, loc="left")
            _rotular_x(eixo["mensal"], dm)
        if vi:
            eixo["doze"].plot(range(len(vi)), vi, color=AZUL, linewidth=2,
                              marker="o", markersize=3)
            eixo["doze"].axhline(0, color="#64748b", linewidth=0.8)
            eixo["doze"].set_title("Acumulado em 12 meses (%)", fontsize=10, loc="left")
            _rotular_x(eixo["doze"], di)

        fig.suptitle(titulo or f"{indicador.upper()} — variações", fontweight="bold")
        fig.tight_layout()

        DATA_DIR.mkdir(exist_ok=True)
        destino = DATA_DIR / f"variacoes_{indicador}.png"
        fig.savefig(destino, dpi=120, bbox_inches="tight")
    except OSError as erro:
        return {"erro": f"não consegui salvar o gráfico em {destino}: {erro}"}
    finally:
        plt.close(fig)  # fecha SEMPRE — sem isso, rodadas seguidas vazam memória

    return {"arquivo": str(destino), "n_mensal": len(vm), "n_interanual": len(vi)}


def _rotular_x(ax, rotulos: list[str]) -> None:
    """Põe poucos rótulos de mês no eixo x, para não virar borrão."""
    ax.grid(True, axis="y", alpha=0.2)
    if not rotulos:
        return
    # No máximo ~8 marcas, espaçadas, para o eixo ficar legível.
    passo = max(1, len(rotulos) // 8)
    pos = list(range(0, len(rotulos), passo))
    ax.set_xticks(pos)
    ax.set_xticklabels([rotulos[i] for i in pos], rotation=45, fontsize=7, ha="right")
