from __future__ import annotations

import json

import pandas as pd
import plotly.graph_objects as go
import pytz
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
from django.db.models import QuerySet

from .models import ImportacaoArquivo, Operacao, SessaoOperacao
from .services import importar_csv  # noqa: F401 — ajuste se necessário

# ──────────────────────────────────────────────
# Constantes
# ──────────────────────────────────────────────

TZ_BR = pytz.timezone("America/Sao_Paulo")

# Agrupamento de futuros por prefixo (quantidade de chars do prefixo)
AGRUPAMENTO_ATIVOS: dict[str, int] = {
    "WIN": 3,
    "WDO": 3,
    "IND": 3,
    "DOL": 3,
}

# Paleta — deve bater com as CSS vars do base.html
COR_POSITIVO = "#3fb68b"
COR_NEGATIVO = "#e05c5c"
COR_AZUL = "#388bfd"
COR_TEXTO = "#b8c4ce"
COR_GRADE = "rgba(48,54,61,0.5)"
BG_GRAFICO = "rgba(0,0,0,0)"   # transparente (o card dá o fundo)
PLOTLY_FONT = dict(family="JetBrains Mono, monospace",
                   color=COR_TEXTO, size=11)

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _agrupar_ativo(nome: str) -> str:
    """Retorna o prefixo agrupado ou o nome completo."""
    for prefixo, n in AGRUPAMENTO_ATIVOS.items():
        if nome.upper().startswith(prefixo):
            return prefixo
    return nome


def _layout_base(**kwargs) -> dict:
    """Layout Plotly padrão para todos os gráficos."""
    base = dict(
        paper_bgcolor=BG_GRAFICO,
        plot_bgcolor=BG_GRAFICO,
        font=PLOTLY_FONT,
        margin=dict(l=10, r=10, t=10, b=10),
        showlegend=False,
        xaxis=dict(
            gridcolor=COR_GRADE,
            zerolinecolor=COR_GRADE,
            showgrid=True,
        ),
        yaxis=dict(
            gridcolor=COR_GRADE,
            zerolinecolor=COR_GRADE,
            showgrid=True,
        ),
    )
    base.update(kwargs)
    return base


def _to_html(fig: go.Figure) -> str:
    """Converte figura para HTML sem incluir Plotly.js."""
    return fig.to_html(
        full_html=False,
        include_plotlyjs=False,
        config={"displaylogo": False, "responsive": True},
    )


def _filtrar_operacoes(request) -> tuple[str, str, QuerySet]:
    """
    Lê data_inicio / data_fim da query string, aplica filtros e
    retorna (data_inicio_str, data_fim_str, queryset).

    Regra crítica: filtros são aplicados com abertura__date__gte/lte
    para comparar só a parte de data (sem timezone no lookup).
    """
    data_inicio = request.GET.get("data_inicio", "").strip()
    data_fim = request.GET.get("data_fim",    "").strip()

    qs = Operacao.objects.all()
    if data_inicio:
        qs = qs.filter(abertura__date__gte=data_inicio)
    if data_fim:
        qs = qs.filter(abertura__date__lte=data_fim)

    return data_inicio, data_fim, qs


def _qs_to_df(qs) -> pd.DataFrame:
    """
    Converte queryset para DataFrame, convertendo datas UTC → BRT.

    Regra crítica: uma única chamada .values() com todos os campos.
    """
    campos = [
        "id", "ativo", "lado", "abertura", "fechamento",
        "tempo_operacao", "qtd_compra", "qtd_venda",
        "preco_compra", "preco_venda",
        "resultado_operacao", "total_acumulado",
        "sessao__data_sessao",
    ]
    registros = list(qs.values(*campos))
    if not registros:
        return pd.DataFrame()

    df = pd.DataFrame(registros)

    # Converter UTC → BRT (regra crítica)
    df["abertura"] = pd.to_datetime(
        df["abertura"], utc=True).dt.tz_convert(TZ_BR)

    # Coluna de ativo agrupado
    df["ativo_grupo"] = df["ativo"].apply(_agrupar_ativo)

    return df


# ──────────────────────────────────────────────
# Gráficos
# ──────────────────────────────────────────────

def _grafico_capital(df: pd.DataFrame) -> str:
    """
    Curva de Capital: linha + área verde/vermelha.

    Regra crítica:
    - converter datas para string via strftime (sem tz no Plotly)
    - type='category' no xaxis
    - definir yaxis range explícito para negativos aparecerem
    """
    if df.empty:
        return ""

    df_sorted = df.sort_values("abertura")
    datas_str = df_sorted["abertura"].dt.strftime("%d/%m %H:%M").tolist()
    acumulado = df_sorted["total_acumulado"].astype(float).tolist()

    ymin = min(acumulado) * \
        1.15 if min(acumulado) < 0 else min(acumulado) * 0.85
    ymax = max(acumulado) * \
        1.15 if max(acumulado) > 0 else max(acumulado) * 0.85
    # Garante margem mínima
    if ymin == ymax:
        ymin -= 100
        ymax += 100

    # Área abaixo da curva — cor depende do último valor
    cor_linha = COR_POSITIVO if acumulado[-1] >= 0 else COR_NEGATIVO
    cor_fill = "rgba(63,182,139,0.12)" if acumulado[-1] >= 0 else "rgba(224,92,92,0.12)"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=datas_str,
        y=acumulado,
        mode="lines",
        line=dict(color=cor_linha, width=2),
        fill="tozeroy",
        fillcolor=cor_fill,
        hovertemplate="<b>%{x}</b><br>Acumulado: R$ %{y:,.2f}<extra></extra>",
    ))
    # Linha zero
    fig.add_hline(y=0, line_color=COR_GRADE, line_width=1)

    fig.update_layout(**_layout_base(
        height=280,
        xaxis=dict(
            type="category",
            gridcolor=COR_GRADE,
            showgrid=False,
            tickangle=-45,
            tickfont=dict(size=9),
        ),
        yaxis=dict(
            gridcolor=COR_GRADE,
            zerolinecolor=COR_GRADE,
            range=[ymin, ymax],
            tickprefix="R$ ",
            tickformat=",.0f",
        ),
    ))
    return _to_html(fig)


def _grafico_horario(df: pd.DataFrame) -> str:
    """
    Resultado por Horário: barras verticais agrupadas por hora cheia.
    """
    if df.empty:
        return ""

    df2 = df.copy()
    df2["hora"] = df2["abertura"].dt.strftime("%H:00")
    agrupado = (
        df2.groupby("hora")["resultado_operacao"]
        .sum()
        .reset_index()
        .sort_values("hora")
    )

    cores = [COR_POSITIVO if v >= 0 else COR_NEGATIVO
             for v in agrupado["resultado_operacao"]]

    fig = go.Figure(go.Bar(
        x=agrupado["hora"].tolist(),
        y=agrupado["resultado_operacao"].astype(float).tolist(),
        marker_color=cores,
        hovertemplate="<b>%{x}</b><br>Resultado: R$ %{y:,.2f}<extra></extra>",
    ))
    fig.update_layout(**_layout_base(
        height=280,
        xaxis=dict(type="category", gridcolor=COR_GRADE, showgrid=False),
        yaxis=dict(
            gridcolor=COR_GRADE,
            zerolinecolor=COR_GRADE,
            tickprefix="R$ ",
            tickformat=",.0f",
        ),
    ))
    return _to_html(fig)


def _grafico_ativos(df: pd.DataFrame) -> str:
    """
    Resultado por Ativo: barras horizontais agrupadas por instrumento.
    """
    if df.empty:
        return ""

    agrupado = (
        df.groupby("ativo_grupo")["resultado_operacao"]
        .sum()
        .reset_index()
        .sort_values("resultado_operacao")
    )

    cores = [COR_POSITIVO if v >= 0 else COR_NEGATIVO
             for v in agrupado["resultado_operacao"]]

    fig = go.Figure(go.Bar(
        x=agrupado["resultado_operacao"].astype(float).tolist(),
        y=agrupado["ativo_grupo"].tolist(),
        orientation="h",
        marker_color=cores,
        hovertemplate="<b>%{y}</b><br>Resultado: R$ %{x:,.2f}<extra></extra>",
    ))
    fig.update_layout(**_layout_base(
        height=280,
        xaxis=dict(
            gridcolor=COR_GRADE,
            zerolinecolor=COR_GRADE,
            tickprefix="R$ ",
            tickformat=",.0f",
        ),
        yaxis=dict(gridcolor=COR_GRADE, showgrid=False),
    ))
    return _to_html(fig)


def _grafico_heatmap(df: pd.DataFrame) -> str:
    """
    Heat Map Dia × Horário.
 
    zmid=0 força o centro da escala no zero.
    Cor central = #161b22 (fundo do card) → células com zero
    ficam "invisíveis", sem dar falsa impressão de resultado negativo.
    """
    if df.empty:
        return ""

    df2 = df.copy()
    df2["hora"] = df2["abertura"].dt.strftime("%H:00")
    df2["dia_semana"] = df2["abertura"].dt.strftime("%A")

    DIAS_PT = {
        "Monday":    "Seg",
        "Tuesday":   "Ter",
        "Wednesday": "Qua",
        "Thursday":  "Qui",
        "Friday":    "Sex",
    }
    df2["dia_pt"] = df2["dia_semana"].map(DIAS_PT).fillna(df2["dia_semana"])

    pivot = (
        df2.groupby(["dia_pt", "hora"])["resultado_operacao"]
        .sum()
        .unstack(fill_value=0)
    )

    ordem_dias = ["Seg", "Ter", "Qua", "Qui", "Sex"]
    pivot = pivot.reindex([d for d in ordem_dias if d in pivot.index])

    fig = go.Figure(go.Heatmap(
        z=pivot.values.tolist(),
        x=pivot.columns.tolist(),
        y=pivot.index.tolist(),
        zmid=0,                         # ← centro da escala fixo no zero
        colorscale=[
            [0.0, COR_NEGATIVO],        # mínimo → vermelho
            [0.5, "#161b22"],           # zero   → cor do fundo do card
            [1.0, COR_POSITIVO],        # máximo → verde
        ],
        hovertemplate="<b>%{y} %{x}</b><br>Resultado: R$ %{z:,.2f}<extra></extra>",
        showscale=True,
        colorbar=dict(
            tickfont=dict(size=9, color=COR_TEXTO),
            tickprefix="R$",
            outlinewidth=0,
            len=0.8,
        ),
    ))
    fig.update_layout(**_layout_base(
        height=280,
        xaxis=dict(type="category", gridcolor=COR_GRADE, showgrid=False),
        yaxis=dict(gridcolor=COR_GRADE, showgrid=False),
    ))
    return _to_html(fig)


# ──────────────────────────────────────────────
# Views
# ──────────────────────────────────────────────

def dashboard(request):
    """
    Página principal: filtros + cards + 4 gráficos Plotly.
    """
    data_inicio, data_fim, qs = _filtrar_operacoes(request)

    df = _qs_to_df(qs)

    # Métricas
    if df.empty:
        resultado_total = 0
        total_operacoes = 0
        total_wins = 0
        total_losses = 0
        win_rate = 0.0
        melhor_op = 0.0
        pior_op = 0.0
        total_sessoes = 0
    else:
        resultado_total = float(df["resultado_operacao"].sum())
        total_operacoes = len(df)
        wins = df["resultado_operacao"] > 0
        total_wins = int(wins.sum())
        total_losses = int((df["resultado_operacao"] <= 0).sum())
        win_rate = (total_wins / total_operacoes *
                    100) if total_operacoes else 0.0
        melhor_op = float(df["resultado_operacao"].max())
        pior_op = float(df["resultado_operacao"].min())
        total_sessoes = df["sessao__data_sessao"].nunique()

    context = {
        # Filtros
        "data_inicio": data_inicio,
        "data_fim":    data_fim,
        # Cards
        "resultado_total": resultado_total,
        "total_operacoes": total_operacoes,
        "total_wins":      total_wins,
        "total_losses":    total_losses,
        "win_rate":        round(win_rate, 1),
        "melhor_op":       melhor_op,
        "pior_op":         pior_op,
        "total_sessoes":   total_sessoes,
        # Gráficos
        "grafico_capital": _grafico_capital(df),
        "grafico_horario": _grafico_horario(df),
        "grafico_ativos":  _grafico_ativos(df),
        "grafico_heatmap": _grafico_heatmap(df),
    }
    return render(request, "trades/dashboard.html", context)


def operacoes(request):
    """
    Tabela de operações com filtros por período e instrumento.
    """
    data_inicio, data_fim, qs = _filtrar_operacoes(request)
    instrumento = request.GET.get("instrumento", "").strip()

    if instrumento:
        qs = qs.filter(ativo__startswith=instrumento)

    # Lista de ativos disponíveis para o select (agrupados)
    todos_ativos = (
        Operacao.objects
        .values_list("ativo", flat=True)
        .distinct()
        .order_by("ativo")
    )
    ativos_agrupados = sorted({_agrupar_ativo(a) for a in todos_ativos})

    # Uma única chamada .values()
    campos = [
        "id", "ativo", "lado", "abertura", "fechamento",
        "tempo_operacao", "qtd_compra", "qtd_venda",
        "preco_compra", "preco_venda",
        "resultado_operacao", "total_acumulado",
    ]
    registros = list(qs.order_by("-abertura").values(*campos))

    # Conversão timezone e métricas
    resultados = []
    total_res = 0.0
    total_wins = 0
    total_losses = 0

    for r in registros:
        abertura_utc = r["abertura"]
        if abertura_utc and hasattr(abertura_utc, "astimezone"):
            abertura_local = abertura_utc.astimezone(TZ_BR)
        else:
            abertura_local = abertura_utc

        res = float(r["resultado_operacao"] or 0)
        total_res += res
        if res > 0:
            total_wins += 1
        else:
            total_losses += 1

        resultados.append({**r, "abertura_local": abertura_local})

    total_operacoes = len(resultados)
    win_rate = (total_wins / total_operacoes * 100) if total_operacoes else 0.0

    context = {
        "data_inicio":          data_inicio,
        "data_fim":             data_fim,
        "instrumento":          instrumento,
        "ativos_disponiveis":   ativos_agrupados,
        "operacoes":            resultados,
        "total_operacoes":      total_operacoes,
        "resultado_total":      round(total_res, 2),
        "total_wins":           total_wins,
        "total_losses":         total_losses,
        "win_rate":             round(win_rate, 1),
    }
    return render(request, "trades/operacoes.html", context)


def importar(request):
    """
    Upload de CSV exportado do Profitchart.
    """
    resultado = None
    erro = None

    if request.method == "POST":
        arquivo = request.FILES.get("arquivo")
        if not arquivo:
            erro = "Nenhum arquivo enviado."
        else:
            try:
                # importar_csv deve estar implementado em services.py
                importacao = importar_csv(arquivo)
                resultado = importacao
                messages.success(
                    request,
                    f"{importacao.total_operacoes} operações importadas com sucesso.",
                )
            except Exception as exc:  # noqa: BLE001
                erro = str(exc)
                messages.error(request, erro)

    importacoes = ImportacaoArquivo.objects.order_by("-importado_em")[:10]

    context = {
        "resultado":   resultado,
        "erro":        erro,
        "importacoes": importacoes,
    }
    return render(request, "trades/importar.html", context)
