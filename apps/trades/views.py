from __future__ import annotations
import numpy as np

import json

import datetime
import pandas as pd
import plotly.graph_objects as go
import pytz
from django.core.paginator import Paginator
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
# Helpers de cálculo — usados só na view dia()
# ──────────────────────────────────────────────

def _calcular_tempo_medio_str(minutos_lista: list[float]) -> str:
    """Converte lista de minutos em string 'Xh Ym' ou 'Ym Zs'."""
    if not minutos_lista:
        return "—"
    media = sum(minutos_lista) / len(minutos_lista)
    h = int(media // 60)
    m = int(media % 60)
    s = int((media * 60) % 60)
    if h > 0:
        return f"{h}h {m}m"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


def _drawdown_pico(acumulados: list[float]) -> float:
    """Maior recuo a partir do pico atingido (clássico max drawdown)."""
    if not acumulados:
        return 0.0
    pico = acumulados[0]
    dd = 0.0
    for v in acumulados:
        if v > pico:
            pico = v
        recuo = v - pico
        if recuo < dd:
            dd = recuo
    return dd


def _minimo_dia(acumulados: list[float]) -> float:
    """Menor valor abaixo de zero atingido no dia; 0 se nunca negativo."""
    minimo = min(acumulados) if acumulados else 0.0
    return minimo if minimo < 0 else 0.0


# ──────────────────────────────────────────────
# Helper de métricas avançadas
# ──────────────────────────────────────────────

def _calcular_metricas_avancadas(df: pd.DataFrame) -> dict:
    """
    Calcula Expectativa Matemática e Payoff Ratio (R Múltiplo Médio).

    Expectativa Matemática (EM):
        EM = (win_rate × gain_médio) − (loss_rate × |loss_médio|)
        Representa o retorno esperado por operação.
        Positiva = estratégia lucrativa no longo prazo.

    Payoff Ratio (R Múltiplo Médio):
        Payoff = gain_médio / |loss_médio|
        Razão entre o que se ganha nas vencedoras vs. o que se perde nas perdedoras.
        Ex.: 1.5 significa que em média ganha-se 1.5× o que se perde.

    Retorna dict com as chaves:
        expectativa_matematica  → float | None
        payoff_ratio            → float | None
        gain_medio              → float | None
        loss_medio              → float | None  (valor negativo)
    """
    if df.empty:
        return {
            "expectativa_matematica": None,
            "payoff_ratio": None,
            "gain_medio": None,
            "loss_medio": None,
        }

    resultados = df["resultado_operacao"].astype(float)
    total = len(resultados)

    wins_mask = resultados > 0
    losses_mask = resultados <= 0

    n_wins = int(wins_mask.sum())
    n_losses = int(losses_mask.sum())

    if n_wins == 0 or n_losses == 0:
        # Sem wins ou sem losses → métricas sem sentido estatístico
        return {
            "expectativa_matematica": None,
            "payoff_ratio": None,
            "gain_medio": float(resultados[wins_mask].mean()) if n_wins else None,
            "loss_medio": float(resultados[losses_mask].mean()) if n_losses else None,
        }

    win_rate = n_wins / total
    loss_rate = n_losses / total

    gain_medio = float(resultados[wins_mask].mean())    # positivo
    loss_medio = float(resultados[losses_mask].mean())  # negativo

    # EM = (P_win × avg_gain) + (P_loss × avg_loss)
    # Como loss_medio já é negativo, a subtração é implícita na soma
    expectativa = round((win_rate * gain_medio) + (loss_rate * loss_medio), 2)

    # Payoff = avg_gain / |avg_loss|
    payoff = round(gain_medio / abs(loss_medio), 2)

    return {
        "expectativa_matematica": expectativa,
        "payoff_ratio": payoff,
        "gain_medio": round(gain_medio, 2),
        "loss_medio": round(loss_medio, 2),
    }


# ──────────────────────────────────────────────
# Gráficos
# ──────────────────────────────────────────────


def _grafico_capital(df: pd.DataFrame) -> str:
    """
    Curva de Capital: linha principal + área verde para lucro / vermelha para prejuízo.

    Regra crítica:
    - converter datas para string via strftime (sem tz no Plotly)
    - type='category' no xaxis
    - definir yaxis range explícito para negativos aparecerem
    """
    if df.empty:
        return ""

    df_sorted = df.sort_values("abertura")
    datas_str = df_sorted["abertura"].dt.strftime("%d/%m %H:%M").tolist()

    # Converte para array numpy para facilitar o filtro de positivos/negativos
    acumulado_array = np.array(df_sorted["total_acumulado"].astype(float))
    acumulado = acumulado_array.tolist()

    ymin = min(acumulado) * \
        1.15 if min(acumulado) < 0 else min(acumulado) * 0.85
    ymax = max(acumulado) * \
        1.15 if max(acumulado) > 0 else max(acumulado) * 0.85

    # Garante margem mínima
    if ymin == ymax:
        ymin -= 100
        ymax += 100

    # Criação das máscaras para áreas de preenchimento
    acumulado_pos = np.where(acumulado_array > 0, acumulado_array, 0).tolist()
    acumulado_neg = np.where(acumulado_array < 0, acumulado_array, 0).tolist()

    # Mantém a sua lógica para a cor da linha principal
    cor_linha = COR_POSITIVO if acumulado[-1] >= 0 else COR_NEGATIVO

    fig = go.Figure()

    # 1. TRACE DA ÁREA POSITIVA (Verde)
    fig.add_trace(go.Scatter(
        x=datas_str,
        y=acumulado_pos,
        mode="lines",
        fill="tozeroy",
        fillcolor="rgba(63,182,139,0.12)",  # Seu verde com transparência
        line=dict(width=0),  # Oculta a linha
        hoverinfo="skip",  # Ignora o tooltip nesta camada
        showlegend=False
    ))

    # 2. TRACE DA ÁREA NEGATIVA (Vermelha)
    fig.add_trace(go.Scatter(
        x=datas_str,
        y=acumulado_neg,
        mode="lines",
        fill="tozeroy",
        fillcolor="rgba(224,92,92,0.12)",  # Seu vermelho com transparência
        line=dict(width=0),  # Oculta a linha
        hoverinfo="skip",
        showlegend=False
    ))

    # 3. TRACE DA LINHA PRINCIPAL
    fig.add_trace(go.Scatter(
        x=datas_str,
        y=acumulado,
        mode="lines",
        line=dict(color=cor_linha, width=2),
        hovertemplate="<b>%{x}</b><br>Acumulado: R$ %{y:,.2f}<extra></extra>",
        showlegend=False
    ))

    # Linha zero
    fig.add_hline(y=0, line_color=COR_GRADE, line_width=1)

    # Layout base
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
# Gráficos exclusivos da página de dia
# ──────────────────────────────────────────────


def _grafico_capital_dia(df: pd.DataFrame) -> str:
    """Curva de Capital intraday — idêntica à do dashboard mas com
    horário exato no eixo X (HH:MM em vez de dd/mm HH:MM)."""
    if df.empty:
        return ""

    df_s = df.sort_values("abertura").reset_index(drop=True)
    # Eixo X: só horário — mais legível para um único dia
    xs = df_s["abertura"].dt.strftime("%H:%M").tolist()

    # Converte para array numpy para aplicar a regra de positivo/negativo
    ys_array = np.array(df_s["total_acumulado"].astype(float))
    ys = ys_array.tolist()

    ymin = min(ys)
    ymax = max(ys)
    margem = (ymax - ymin) * 0.18 if ymax != ymin else 100
    ymin -= margem
    ymax += margem

    # Criação das máscaras para áreas de preenchimento
    ys_pos = np.where(ys_array > 0, ys_array, 0).tolist()
    ys_neg = np.where(ys_array < 0, ys_array, 0).tolist()

    # Cor da linha e marcadores baseada no saldo final do dia
    cor_linha = COR_POSITIVO if ys[-1] >= 0 else COR_NEGATIVO

    fig = go.Figure()

    # 1. TRACE DA ÁREA POSITIVA (Verde)
    fig.add_trace(go.Scatter(
        x=xs,
        y=ys_pos,
        mode="lines",
        fill="tozeroy",
        fillcolor="rgba(63,182,139,0.12)",
        line=dict(width=0),  # Sem linha ou marcador, apenas preenchimento
        hoverinfo="skip",
        showlegend=False
    ))

    # 2. TRACE DA ÁREA NEGATIVA (Vermelha)
    fig.add_trace(go.Scatter(
        x=xs,
        y=ys_neg,
        mode="lines",
        fill="tozeroy",
        fillcolor="rgba(224,92,92,0.12)",
        line=dict(width=0),  # Sem linha ou marcador, apenas preenchimento
        hoverinfo="skip",
        showlegend=False
    ))

    # 3. TRACE DA LINHA PRINCIPAL (Com os marcadores)
    fig.add_trace(go.Scatter(
        x=xs,
        y=ys,
        mode="lines+markers",  # Mantido para destacar as operações do dia
        line=dict(color=cor_linha, width=2),
        marker=dict(size=5, color=cor_linha),
        hovertemplate="<b>%{x}</b><br>Acumulado: R$ %{y:,.2f}<extra></extra>",
        showlegend=False
    ))

    # Linha zero
    fig.add_hline(y=0, line_color=COR_GRADE, line_width=1)

    fig.update_layout(**_layout_base(
        height=260,
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


def _grafico_horario_dia(df: pd.DataFrame) -> str:
    """Resultado por horário (barras) — mesmo padrão do dashboard."""
    if df.empty:
        return ""

    df2 = df.copy()
    df2["hora"] = df2["abertura"].dt.strftime("%H:%M")
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
        height=260,
        xaxis=dict(type="category", gridcolor=COR_GRADE, showgrid=False,
                   tickangle=-45, tickfont=dict(size=9)),
        yaxis=dict(
            gridcolor=COR_GRADE,
            zerolinecolor=COR_GRADE,
            tickprefix="R$ ",
            tickformat=",.0f",
        ),
    ))
    return _to_html(fig)


def _grafico_execucao(df: pd.DataFrame) -> str:
    """
    Análise de Execução — MEP × MEN × Resultado por operação.

    Cada operação vira uma linha horizontal com 3 elementos:
      • Barra azul:  do zero até o resultado final (gain ou loss)
      • Marcador ▲:  MEP (máxima exposição positiva atingida)
      • Marcador ▼:  MEN (máxima exposição negativa atingida)

    Eixo Y: label com horário + ativo.
    Eixo X: valores em R$.
    """
    if df.empty:
        return ""

    df_s = df.sort_values("abertura").reset_index(drop=True)

    labels = (df_s["abertura"].dt.strftime(
        "%H:%M") + " " + df_s["ativo"]).tolist()
    resultados = df_s["resultado_operacao"].astype(float).tolist()
    meps = df_s["mep"].astype(float).tolist()
    mens = df_s["men"].astype(float).tolist()

    cores_barra = [COR_POSITIVO if r >=
                   0 else COR_NEGATIVO for r in resultados]

    fig = go.Figure()

    # Barras do resultado final
    fig.add_trace(go.Bar(
        x=resultados,
        y=labels,
        orientation="h",
        marker_color=cores_barra,
        marker_opacity=0.85,
        name="Resultado",
        hovertemplate="<b>%{y}</b><br>Resultado: R$ %{x:,.2f}<extra></extra>",
    ))

    # MEP — marcador triangular verde
    fig.add_trace(go.Scatter(
        x=meps,
        y=labels,
        mode="markers",
        marker=dict(symbol="triangle-right", size=10,
                    color=COR_POSITIVO, line=dict(width=1, color="#0d1117")),
        name="MEP",
        hovertemplate="<b>%{y}</b><br>MEP: R$ %{x:,.2f}<extra></extra>",
    ))

    # MEN — marcador triangular vermelho
    fig.add_trace(go.Scatter(
        x=mens,
        y=labels,
        mode="markers",
        marker=dict(symbol="triangle-left", size=10,
                    color=COR_NEGATIVO, line=dict(width=1, color="#0d1117")),
        name="MEN",
        hovertemplate="<b>%{y}</b><br>MEN: R$ %{x:,.2f}<extra></extra>",
    ))

    # Altura dinâmica: mínimo 260px, +30px por operação
    altura = max(260, 80 + len(labels) * 38)

    fig.update_layout(**_layout_base(
        height=altura,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="right",  x=1,
            font=dict(size=10, color=COR_TEXTO),
        ),
        xaxis=dict(
            gridcolor=COR_GRADE,
            zerolinecolor=COR_GRADE,
            tickprefix="R$ ",
            tickformat=",.0f",
        ),
        yaxis=dict(gridcolor=COR_GRADE, showgrid=False),
        barmode="overlay",
    ))
    return _to_html(fig)


# ──────────────────────────────────────────────
# Views
# ──────────────────────────────────────────────

def dashboard(request):
    """
    Página principal: filtros + cards + métricas avançadas + 4 gráficos Plotly.
    """
    data_inicio, data_fim, qs = _filtrar_operacoes(request)

    df = _qs_to_df(qs)

    # Métricas base
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

    # Métricas avançadas
    metricas_av = _calcular_metricas_avancadas(df)

    context = {
        # Filtros
        "data_inicio": data_inicio,
        "data_fim":    data_fim,
        # Cards base
        "resultado_total": resultado_total,
        "total_operacoes": total_operacoes,
        "total_wins":      total_wins,
        "total_losses":    total_losses,
        "win_rate":        round(win_rate, 1),
        "melhor_op":       melhor_op,
        "pior_op":         pior_op,
        "total_sessoes":   total_sessoes,
        # Métricas avançadas
        "expectativa_matematica": metricas_av["expectativa_matematica"],
        "payoff_ratio":           metricas_av["payoff_ratio"],
        "gain_medio":             metricas_av["gain_medio"],
        "loss_medio":             metricas_av["loss_medio"],
        # Gráficos
        "grafico_capital": _grafico_capital(df),
        "grafico_horario": _grafico_horario(df),
        "grafico_ativos":  _grafico_ativos(df),
        "grafico_heatmap": _grafico_heatmap(df),
    }
    return render(request, "trades/dashboard.html", context)


def operacoes(request):
    """
    Tabela de operações com filtros por período e instrumento + paginação.
    """
    data_inicio, data_fim, qs = _filtrar_operacoes(request)
    instrumento = request.GET.get("instrumento", "").strip()
    por_pagina = request.GET.get("por_pagina",  "10").strip()

    # Garante que por_pagina seja um inteiro válido dentro das opções aceitas
    OPCOES_POR_PAGINA = [10, 20, 50, 100]
    try:
        por_pagina = int(por_pagina)
        if por_pagina not in OPCOES_POR_PAGINA:
            por_pagina = 10
    except (ValueError, TypeError):
        por_pagina = 10

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

    # Uma única chamada .values() — mais recente primeiro
    campos = [
        "id", "ativo", "lado", "abertura", "fechamento",
        "tempo_operacao", "qtd_compra", "qtd_venda",
        "preco_compra", "preco_venda",
        "resultado_operacao", "total_acumulado",
    ]
    registros = list(qs.order_by("-abertura").values(*campos))

    # Métricas totais (sobre todos os registros, não só a página atual)
    total_operacoes = len(registros)
    total_res = 0.0
    total_wins = 0
    total_losses = 0

    for r in registros:
        res = float(r["resultado_operacao"] or 0)
        total_res += res
        if res > 0:
            total_wins += 1
        else:
            total_losses += 1

    win_rate = (total_wins / total_operacoes * 100) if total_operacoes else 0.0

    # Conversão de timezone em todos os registros
    registros_cronologicos = list(reversed(registros))
    acumulado_periodo = 0.0
    registros_conv = []

    for r in registros_cronologicos:
        abertura_utc = r["abertura"]
        if abertura_utc and hasattr(abertura_utc, "astimezone"):
            abertura_local = abertura_utc.astimezone(TZ_BR)
        else:
            abertura_local = abertura_utc

        acumulado_periodo += float(r["resultado_operacao"] or 0)

        registros_conv.append({
            **r,
            "abertura_local":  abertura_local,
            # sobrescreve o do banco
            "total_acumulado": round(acumulado_periodo, 2),
        })

    # Reverter para exibição: mais recente primeiro
    registros_conv = list(reversed(registros_conv))

    # Paginação
    paginator = Paginator(registros_conv, por_pagina)
    pagina_num = request.GET.get("pagina", 1)
    try:
        pagina_num = int(pagina_num)
    except (ValueError, TypeError):
        pagina_num = 1

    pagina_obj = paginator.get_page(pagina_num)

    # Intervalo de páginas exibidas na barra (máximo 5 botões numéricos)
    num_pages = paginator.num_pages
    pagina_atual = pagina_obj.number
    inicio = max(1, pagina_atual - 2)
    fim = min(num_pages, pagina_atual + 2)
    # Ajusta para sempre tentar mostrar 5 botões
    if fim - inicio < 4:
        if inicio == 1:
            fim = min(num_pages, inicio + 4)
        else:
            inicio = max(1, fim - 4)
    intervalo_paginas = range(inicio, fim + 1)

    # Parâmetros GET sem 'pagina' (para links de paginação não quebrarem filtros)
    get_sem_pagina = request.GET.copy()
    get_sem_pagina.pop("pagina", None)
    query_string = get_sem_pagina.urlencode()

    context = {
        "data_inicio":          data_inicio,
        "data_fim":             data_fim,
        "instrumento":          instrumento,
        "ativos_disponiveis":   ativos_agrupados,
        "operacoes":            pagina_obj,
        "pagina_obj":           pagina_obj,
        "intervalo_paginas":    intervalo_paginas,
        "query_string":         query_string,
        "total_operacoes":      total_operacoes,
        "resultado_total":      round(total_res, 2),
        "total_wins":           total_wins,
        "total_losses":         total_losses,
        "win_rate":             round(win_rate, 1),
        "por_pagina":           por_pagina,
        "opcoes_por_pagina":    OPCOES_POR_PAGINA,
    }
    return render(request, "trades/operacoes.html", context)


def importar(request):
    """
    Upload de CSV exportado do Profitchart + exclusão de sessões por data/ativo.
    """
    resultado = None
    erro = None

    if request.method == "POST":
        acao = request.POST.get("acao", "importar")

        # ── Exclusão de sessão ──────────────────────────────────────
        if acao == "excluir":
            data_excluir = request.POST.get("data_excluir", "").strip()
            ativo_excluir = request.POST.get("ativo_excluir", "").strip()
            confirmar = request.POST.get("confirmar_exclusao", "")

            if not data_excluir:
                messages.error(request, "Selecione uma data para excluir.")
            elif confirmar != "1":
                messages.warning(
                    request,
                    "Marque a caixa de confirmação antes de excluir."
                )
            else:
                # Filtra operações do dia; se ativo específico, filtra também
                qs_del = Operacao.objects.filter(abertura__date=data_excluir)
                if ativo_excluir and ativo_excluir != "todos":
                    qs_del = qs_del.filter(ativo__startswith=ativo_excluir)

                total_ops = qs_del.count()
                if total_ops == 0:
                    messages.warning(
                        request,
                        f"Nenhuma operação encontrada para {data_excluir}"
                        + (f" / {ativo_excluir}" if ativo_excluir and ativo_excluir != "todos" else "")
                        + "."
                    )
                else:
                    qs_del.delete()

                    # Limpa sessões que ficaram sem operações
                    SessaoOperacao.objects.filter(
                        operacoes__isnull=True
                    ).delete()

                    # Limpa ImportacaoArquivo sem nenhuma operação restante
                    ImportacaoArquivo.objects.filter(
                        operacoes__isnull=True
                    ).delete()

                    descricao = f"{data_excluir}"
                    if ativo_excluir and ativo_excluir != "todos":
                        descricao += f" · {ativo_excluir}"
                    messages.success(
                        request,
                        f"{total_ops} operaç{'ão' if total_ops == 1 else 'ões'} "
                        f"excluída{'s' if total_ops > 1 else ''} ({descricao})."
                    )
            return redirect("trades:importar")

        # ── Importação de CSV ───────────────────────────────────────
        arquivo = request.FILES.get("arquivo")
        if not arquivo:
            erro = "Nenhum arquivo enviado."
        else:
            try:
                importacao = importar_csv(arquivo)
                resultado = importacao
                messages.success(
                    request,
                    f"{importacao.total_operacoes} operações importadas com sucesso.",
                )
            except Exception as exc:  # noqa: BLE001
                erro = str(exc)
                messages.error(request, erro)

    # ── Dados para o template ───────────────────────────────────────
    importacoes = ImportacaoArquivo.objects.order_by("-importado_em")[:10]

    # Dias disponíveis no banco para o seletor de exclusão
    dias_no_banco = (
        Operacao.objects
        .dates("abertura", "day", order="DESC")
    )
    dias_exclusao = [d.strftime("%Y-%m-%d") for d in dias_no_banco]

    # Ativos agrupados por dia — para o select dinâmico de ativo
    # Formato: {"2025-11-01": ["WIN", "WDO"], ...}
    ativos_por_dia: dict[str, list[str]] = {}
    ops_por_dia = (
        Operacao.objects
        .values("abertura__date", "ativo")
        .distinct()
        .order_by("abertura__date", "ativo")
    )
    for row in ops_por_dia:
        dia_str = row["abertura__date"].strftime("%Y-%m-%d")
        grupo = _agrupar_ativo(row["ativo"])
        dia_list = ativos_por_dia.setdefault(dia_str, [])
        if grupo not in dia_list:
            dia_list.append(grupo)

    context = {
        "resultado":      resultado,
        "erro":           erro,
        "importacoes":    importacoes,
        "dias_exclusao":  dias_exclusao,
        "ativos_por_dia": json.dumps(ativos_por_dia),  # serializado p/ JS
    }
    return render(request, "trades/importar.html", context)


# ──────────────────────────────────────────────
# View Dia
# ──────────────────────────────────────────────

def dia(request):
    """
    Análise detalhada de um dia de pregão.
    Parâmetro GET: data (YYYY-MM-DD). Se ausente, usa o dia mais recente.
    """
    # Todos os dias com operações (para o seletor do sidebar)
    dias_disponiveis = (
        Operacao.objects
        .dates("abertura", "day", order="DESC")
    )
    # Converte para lista de strings YYYY-MM-DD
    dias_str = [d.strftime("%Y-%m-%d") for d in dias_disponiveis]

    if not dias_str:
        return render(request, "trades/dia.html", {"sem_dados": True})

    # Data selecionada — padrão: mais recente
    data_sel = request.GET.get("data", dias_str[0]).strip()
    if data_sel not in dias_str:
        data_sel = dias_str[0]

    # Uma única chamada .values() com todos os campos necessários
    campos = [
        "id", "ativo", "lado", "abertura", "fechamento",
        "tempo_operacao", "qtd_compra", "qtd_venda",
        "preco_compra", "preco_venda", "preco_medio",
        "resultado_operacao", "total_acumulado",
        "mep", "men", "ganho_maximo", "perda_maxima",
    ]
    qs = (
        Operacao.objects
        .filter(abertura__date=data_sel)
        .order_by("abertura")
        .values(*campos)
    )
    registros = list(qs)

    if not registros:
        return render(request, "trades/dia.html", {
            "sem_dados":        False,
            "dias_disponiveis": dias_str,
            "data_sel":         data_sel,
            "sem_ops":          True,
        })

    # ── DataFrame ──
    df = pd.DataFrame(registros)
    df["abertura"] = pd.to_datetime(
        df["abertura"], utc=True).dt.tz_convert(TZ_BR)
    df["resultado_operacao"] = df["resultado_operacao"].astype(float)

    # Recalcular acumulado apenas com as operações do dia (ordem cronológica)
    df = df.sort_values("abertura").reset_index(drop=True)
    df["total_acumulado"] = df["resultado_operacao"].cumsum()

    df["mep"] = df["mep"].astype(float)
    df["men"] = df["men"].astype(float)

    # ── KPIs base ──
    total_ops = len(df)
    resultado = float(df["resultado_operacao"].sum())
    wins_mask = df["resultado_operacao"] > 0
    losses_mask = df["resultado_operacao"] <= 0
    total_wins = int(wins_mask.sum())
    total_losses = int(losses_mask.sum())
    win_rate = (total_wins / total_ops * 100) if total_ops else 0.0

    soma_gains = float(df.loc[wins_mask,   "resultado_operacao"].sum())
    soma_losses = float(df.loc[losses_mask, "resultado_operacao"].sum())
    fator_lucro = (soma_gains / abs(soma_losses)) if soma_losses != 0 else None

    acumulados = df["total_acumulado"].tolist()
    drawdown_max = _drawdown_pico(acumulados)
    exposicao_neg = _minimo_dia(acumulados)

    maior_gain_row = df.loc[df["resultado_operacao"].idxmax()]
    maior_loss_row = df.loc[df["resultado_operacao"].idxmin()]

    maior_gain = float(maior_gain_row["resultado_operacao"])
    maior_gain_ativo = maior_gain_row["ativo"]
    maior_gain_hora = maior_gain_row["abertura"].strftime("%H:%M")

    maior_loss = float(maior_loss_row["resultado_operacao"])
    maior_loss_ativo = maior_loss_row["ativo"]
    maior_loss_hora = maior_loss_row["abertura"].strftime("%H:%M")

    # Tempo médio winners / losers
    df["fechamento_local"] = pd.to_datetime(
        df["fechamento"], utc=True
    ).dt.tz_convert(TZ_BR)
    df["duracao_min"] = (
        (df["fechamento_local"] - df["abertura"]).dt.total_seconds() / 60
    )

    mins_winners = df.loc[wins_mask,   "duracao_min"].tolist()
    mins_losers = df.loc[losses_mask, "duracao_min"].tolist()
    tempo_medio_win = _calcular_tempo_medio_str(mins_winners)
    tempo_medio_loss = _calcular_tempo_medio_str(mins_losers)

    if mins_winners and mins_losers:
        media_w = sum(mins_winners) / len(mins_winners)
        media_l = sum(mins_losers) / len(mins_losers)
        razao = round(media_l / media_w, 1) if media_w else None
    else:
        razao = None

    # ── Métricas avançadas do dia ──
    metricas_av_dia = _calcular_metricas_avancadas(df)

    tabela = []
    for _, row in df.iterrows():
        tabela.append({
            "ativo":              row["ativo"],
            "lado":               row["lado"],
            "abertura_local":     row["abertura"],
            "qtd_compra":         row["qtd_compra"],
            "preco_compra":       row["preco_compra"],
            "preco_venda":        row["preco_venda"],
            "mep":                row["mep"],
            "men":                row["men"],
            "resultado_operacao": row["resultado_operacao"],
            "tempo_operacao":     row["tempo_operacao"],
            "total_acumulado":    row["total_acumulado"],
        })

    context = {
        "sem_dados":         False,
        "sem_ops":           False,
        "dias_disponiveis":  dias_str,
        "data_sel":          data_sel,
        # KPIs linha 1
        "resultado_total":   round(resultado, 2),
        "win_rate":          round(win_rate, 1),
        "total_ops":         total_ops,
        # KPIs linha 2
        "fator_lucro":       round(fator_lucro, 2) if fator_lucro else None,
        "drawdown_max":      round(drawdown_max, 2),
        "exposicao_neg":     round(exposicao_neg, 2),
        # KPIs linha 3
        "maior_gain":        round(maior_gain, 2),
        "maior_gain_ativo":  maior_gain_ativo,
        "maior_gain_hora":   maior_gain_hora,
        "maior_loss":        round(maior_loss, 2),
        "maior_loss_ativo":  maior_loss_ativo,
        "maior_loss_hora":   maior_loss_hora,
        # KPIs linha 4
        "tempo_medio_win":   tempo_medio_win,
        "tempo_medio_loss":  tempo_medio_loss,
        "razao_tempo":       razao,
        "total_wins":        total_wins,
        "total_losses":      total_losses,
        # Métricas avançadas do dia
        "payoff_ratio_dia":           metricas_av_dia["payoff_ratio"],
        "gain_medio_dia":             metricas_av_dia["gain_medio"],
        "loss_medio_dia":             metricas_av_dia["loss_medio"],
        # Gráficos
        "grafico_capital":   _grafico_capital_dia(df),
        "grafico_horario":   _grafico_horario_dia(df),
        "grafico_execucao":  _grafico_execucao(df),
        # Tabela
        "operacoes":         tabela,
    }
    return render(request, "trades/dia.html", context)
