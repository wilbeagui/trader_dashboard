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
from django.shortcuts import render, redirect, get_object_or_404

from .models import ImportacaoArquivo, Operacao, ParametrosTrader, SessaoOperacao, JournalOperacao
from .services import importar_csv  # noqa: F401

# ──────────────────────────────────────────────
# Constantes
# ──────────────────────────────────────────────

TZ_BR = pytz.timezone("America/Sao_Paulo")

AGRUPAMENTO_ATIVOS: dict[str, int] = {
    "WIN": 3,
    "WDO": 3,
    "IND": 3,
    "DOL": 3,
}

COR_POSITIVO = "#3fb68b"
COR_NEGATIVO = "#e05c5c"
COR_AZUL = "#388bfd"
COR_AMARELO = "#e3b341"
COR_TEXTO = "#b8c4ce"
COR_GRADE = "rgba(48,54,61,0.5)"
BG_GRAFICO = "rgba(0,0,0,0)"
PLOTLY_FONT = dict(family="JetBrains Mono, monospace",
                   color=COR_TEXTO, size=11)

# ──────────────────────────────────────────────
# Helpers gerais
# ──────────────────────────────────────────────


def _agrupar_ativo(nome: str) -> str:
    for prefixo, n in AGRUPAMENTO_ATIVOS.items():
        if nome.upper().startswith(prefixo):
            return prefixo
    return nome


def _layout_base(**kwargs) -> dict:
    base = dict(
        paper_bgcolor=BG_GRAFICO,
        plot_bgcolor=BG_GRAFICO,
        font=PLOTLY_FONT,
        margin=dict(l=10, r=10, t=10, b=10),
        showlegend=False,
        xaxis=dict(gridcolor=COR_GRADE,
                   zerolinecolor=COR_GRADE, showgrid=True),
        yaxis=dict(gridcolor=COR_GRADE,
                   zerolinecolor=COR_GRADE, showgrid=True),
    )
    base.update(kwargs)
    return base


def _to_html(fig: go.Figure) -> str:
    return fig.to_html(
        full_html=False,
        include_plotlyjs=False,
        config={"displaylogo": False, "responsive": True},
    )


def _filtrar_operacoes(request) -> tuple[str, str, QuerySet]:
    data_inicio = request.GET.get("data_inicio", "").strip()
    data_fim = request.GET.get("data_fim",    "").strip()
    qs = Operacao.objects.all()
    if data_inicio:
        qs = qs.filter(abertura__date__gte=data_inicio)
    if data_fim:
        qs = qs.filter(abertura__date__lte=data_fim)
    return data_inicio, data_fim, qs


def _qs_to_df(qs) -> pd.DataFrame:
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
    df["abertura"] = pd.to_datetime(
        df["abertura"], utc=True).dt.tz_convert(TZ_BR)
    df["ativo_grupo"] = df["ativo"].apply(_agrupar_ativo)
    return df


# ──────────────────────────────────────────────
# Helpers de cálculo — dia()
# ──────────────────────────────────────────────

def _calcular_tempo_medio_str(minutos_lista: list[float]) -> str:
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
    minimo = min(acumulados) if acumulados else 0.0
    return minimo if minimo < 0 else 0.0


# ──────────────────────────────────────────────
# Métricas avançadas (dashboard + dia)
# ──────────────────────────────────────────────

def _calcular_metricas_avancadas(df: pd.DataFrame) -> dict:
    """
    Expectativa Matemática e Payoff Ratio.

    EM      = (win_rate × gain_médio) + (loss_rate × loss_médio)
    Payoff  = gain_médio / |loss_médio|

    Retorna None quando não há wins e losses simultaneamente.
    """
    if df.empty:
        return {"expectativa_matematica": None, "payoff_ratio": None,
                "gain_medio": None, "loss_medio": None}

    resultados = df["resultado_operacao"].astype(float)
    total = len(resultados)
    wins_mask = resultados > 0
    losses_mask = resultados <= 0
    n_wins = int(wins_mask.sum())
    n_losses = int(losses_mask.sum())

    if n_wins == 0 or n_losses == 0:
        return {"expectativa_matematica": None, "payoff_ratio": None,
                "gain_medio": float(resultados[wins_mask].mean()) if n_wins else None,
                "loss_medio": float(resultados[losses_mask].mean()) if n_losses else None}

    win_rate = n_wins / total
    loss_rate = n_losses / total
    gain_medio = float(resultados[wins_mask].mean())
    loss_medio = float(resultados[losses_mask].mean())

    return {
        "expectativa_matematica": round((win_rate * gain_medio) + (loss_rate * loss_medio), 2),
        "payoff_ratio":           round(gain_medio / abs(loss_medio), 2),
        "gain_medio":             round(gain_medio, 2),
        "loss_medio":             round(loss_medio, 2),
    }


# ──────────────────────────────────────────────
# Indicadores comportamentais
# ──────────────────────────────────────────────

def _calcular_comportamental(df: pd.DataFrame, params: ParametrosTrader) -> dict:
    """
    Calcula os 5 indicadores comportamentais a partir do DataFrame completo
    do período filtrado. Retorna um dict pronto para o context do template.

    Indicadores:
      1. Revenge Trading   — op aberta < params.tempo_minimo_entre_trades min após loss
      2. Overtrading       — dias com > params.max_operacoes_dia operações
      3. Aproveitamento MEP (winners)  — resultado / MEP
      4. Gestão de Stop — MEN (losers) — |MEN| / |resultado|
      5. Consistência / Disciplina     — desvio padrão diário, sequência W/L
    """
    if df.empty:
        return {"sem_dados": True}

    df = df.copy()
    df["resultado_operacao"] = df["resultado_operacao"].astype(float)
    df["mep"] = df["mep"].astype(float)
    df["men"] = df["men"].astype(float)
    df = df.sort_values("abertura").reset_index(drop=True)

    wins_mask = df["resultado_operacao"] > 0
    losses_mask = df["resultado_operacao"] <= 0

    # ── 1. Revenge Trading ─────────────────────────────────────────
    limiar_min = params.tempo_minimo_entre_trades
    revenge_ops = []

    for i in range(1, len(df)):
        op_anterior = df.iloc[i - 1]
        op_atual = df.iloc[i]

        # Só conta se a operação anterior foi uma perda
        if op_anterior["resultado_operacao"] >= 0:
            continue

        diff_min = (
            op_atual["abertura"] - op_anterior["abertura"]
        ).total_seconds() / 60

        if diff_min < limiar_min:
            revenge_ops.append({
                "abertura":    op_atual["abertura"].strftime("%d/%m %H:%M"),
                "ativo":       op_atual["ativo"],
                "resultado":   round(op_atual["resultado_operacao"], 2),
                "intervalo":   round(diff_min, 1),
                "loss_anterior": round(op_anterior["resultado_operacao"], 2),
            })

    revenge_total = len(revenge_ops)
    revenge_resultado = round(sum(r["resultado"] for r in revenge_ops), 2)
    revenge_win_count = sum(1 for r in revenge_ops if r["resultado"] > 0)
    revenge_loss_count = revenge_total - revenge_win_count

    # ── 2. Overtrading ─────────────────────────────────────────────
    limiar_ops = params.max_operacoes_dia

    df["data_dia"] = df["abertura"].dt.date
    ops_por_dia = df.groupby("data_dia").agg(
        total_ops=("resultado_operacao", "count"),
        resultado_dia=("resultado_operacao", "sum"),
    ).reset_index()
    ops_por_dia["resultado_dia"] = ops_por_dia["resultado_dia"].round(2)

    dias_overtrading = ops_por_dia[ops_por_dia["total_ops"] > limiar_ops].copy(
    )
    dias_overtrading["data_str"] = dias_overtrading["data_dia"].apply(
        lambda d: d.strftime("%d/%m/%Y")
    )

    media_ops_dia = round(ops_por_dia["total_ops"].mean(), 1)
    total_dias = len(ops_por_dia)
    n_overtrading = len(dias_overtrading)

    # Dados para gráfico overtrading (ops × resultado por dia)
    ot_datas = ops_por_dia["data_dia"].apply(
        lambda d: d.strftime("%d/%m")).tolist()
    ot_ops = ops_por_dia["total_ops"].tolist()
    ot_resultados = ops_por_dia["resultado_dia"].tolist()

    # ── 3. Aproveitamento do MEP (winners) ─────────────────────────
    df_wins = df[wins_mask & (df["mep"] > 0)].copy()

    if not df_wins.empty:
        df_wins["aproveitamento"] = (
            df_wins["resultado_operacao"] / df_wins["mep"] * 100
        ).round(1)
        aprov_medio = round(df_wins["aproveitamento"].mean(), 1)

        # Top 5 com maior "desperdício" (menor aproveitamento)
        pior_aprov = (
            df_wins.nsmallest(5, "aproveitamento")[
                ["abertura", "ativo", "resultado_operacao", "mep", "aproveitamento"]
            ].copy()
        )
        pior_aprov["abertura_str"] = pior_aprov["abertura"].dt.strftime(
            "%d/%m %H:%M")
        pior_aprov_lista = pior_aprov.to_dict("records")
    else:
        aprov_medio = None
        pior_aprov_lista = []

    # ── 4. Gestão de Stop — MEN (losers) ───────────────────────────
    # men já é negativo no banco; usa valor absoluto para a razão
    df_losses = df[losses_mask & (df["men"] < 0)].copy()

    if not df_losses.empty:
        df_losses["razao_men"] = (
            df_losses["men"].abs() /
            df_losses["resultado_operacao"].abs() * 100
        ).round(1)
        # razao_men > 100% significa que o MEN foi pior que o resultado final
        # (saiu antes do pior momento); = 100% saiu exatamente no fundo
        men_razao_media = round(df_losses["razao_men"].mean(), 1)

        # Top 5 onde saiu mais próximo do pior momento (razao_men >= 80%)
        piores_stop = (
            df_losses.nlargest(5, "razao_men")[
                ["abertura", "ativo", "resultado_operacao", "men", "razao_men"]
            ].copy()
        )
        piores_stop["abertura_str"] = piores_stop["abertura"].dt.strftime(
            "%d/%m %H:%M")
        piores_stop_lista = piores_stop.to_dict("records")
    else:
        men_razao_media = None
        piores_stop_lista = []

    # ── 5. Consistência / Disciplina ───────────────────────────────
    resultado_por_dia = ops_por_dia["resultado_dia"].tolist()
    pct_dias_positivos = (
        round(ops_por_dia[ops_por_dia["resultado_dia"]
              > 0].shape[0] / total_dias * 100, 1)
        if total_dias else 0.0
    )
    desvio_padrao_diario = round(
        float(ops_por_dia["resultado_dia"].std()), 2
    ) if total_dias > 1 else None

    # Sequência atual de dias W/L consecutivos (mais recente primeiro)
    resultados_ordenados = ops_por_dia.sort_values(
        "data_dia", ascending=False
    )["resultado_dia"].tolist()

    sequencia_atual = 0
    sequencia_tipo = None   # "W" ou "L"
    if resultados_ordenados:
        sequencia_tipo = "W" if resultados_ordenados[0] > 0 else "L"
        for r in resultados_ordenados:
            if (sequencia_tipo == "W" and r > 0) or (sequencia_tipo == "L" and r <= 0):
                sequencia_atual += 1
            else:
                break

    # ── Gráfico Overtrading: ops/dia × barra de resultado ──────────
    grafico_overtrading = _grafico_overtrading(
        ot_datas, ot_ops, ot_resultados, limiar_ops
    )

    # ── Gráfico Consistência: resultado diário ──────────────────────
    grafico_consistencia = _grafico_consistencia(ops_por_dia)

    return {
        "sem_dados": False,
        # parâmetros ativos (para exibir no template)
        "limiar_revenge":    limiar_min,
        "limiar_overtrading": limiar_ops,
        # 1. Revenge Trading
        "revenge_total":      revenge_total,
        "revenge_resultado":  revenge_resultado,
        "revenge_win_count":  revenge_win_count,
        "revenge_loss_count": revenge_loss_count,
        "revenge_ops":        revenge_ops,
        # 2. Overtrading
        "media_ops_dia":      media_ops_dia,
        "total_dias":         total_dias,
        "n_overtrading":      n_overtrading,
        "dias_overtrading":   dias_overtrading[
            ["data_str", "total_ops", "resultado_dia"]
        ].to_dict("records"),
        "grafico_overtrading": grafico_overtrading,
        # 3. MEP
        "aprov_medio":        aprov_medio,
        "pior_aprov_lista":   pior_aprov_lista,
        # 4. MEN
        "men_razao_media":    men_razao_media,
        "piores_stop_lista":  piores_stop_lista,
        # 5. Consistência
        "pct_dias_positivos":    pct_dias_positivos,
        "desvio_padrao_diario":  desvio_padrao_diario,
        "sequencia_atual":       sequencia_atual,
        "sequencia_tipo":        sequencia_tipo,
        "grafico_consistencia":  grafico_consistencia,
    }


# ──────────────────────────────────────────────
# Gráficos comportamentais
# ──────────────────────────────────────────────

def _grafico_overtrading(
    datas: list, ops: list, resultados: list, limiar: int
) -> str:
    """
    Gráfico duplo: barras de resultado por dia (eixo Y esquerdo)
    + linha de qtd de operações (eixo Y direito) com linha de limiar.
    """
    if not datas:
        return ""

    cores_barras = [COR_POSITIVO if r >=
                    0 else COR_NEGATIVO for r in resultados]

    fig = go.Figure()

    # Barras de resultado (eixo primário)
    fig.add_trace(go.Bar(
        x=datas,
        y=resultados,
        name="Resultado R$",
        marker_color=cores_barras,
        marker_opacity=0.7,
        yaxis="y",
        hovertemplate="<b>%{x}</b><br>Resultado: R$ %{y:,.2f}<extra></extra>",
    ))

    # Linha de qtd de operações (eixo secundário)
    cores_pontos = [
        COR_NEGATIVO if o > limiar else COR_AZUL for o in ops
    ]
    fig.add_trace(go.Scatter(
        x=datas,
        y=ops,
        name="Operações",
        mode="lines+markers",
        line=dict(color=COR_AZUL, width=2),
        marker=dict(size=7, color=cores_pontos,
                    line=dict(width=1, color="#0d1117")),
        yaxis="y2",
        hovertemplate="<b>%{x}</b><br>Operações: %{y}<extra></extra>",
    ))

    # Linha de limiar no eixo secundário
    fig.add_hline(
        y=limiar,
        line_color=COR_AMARELO,
        line_width=1,
        line_dash="dash",
        annotation_text=f"Limiar ({limiar})",
        annotation_font=dict(size=10, color=COR_AMARELO),
        annotation_position="top right",
        yref="y2",
    )

    fig.update_layout(**_layout_base(
        height=280,
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="right", x=1,
            font=dict(size=10, color=COR_TEXTO),
        ),
        barmode="overlay",
        xaxis=dict(type="category", gridcolor=COR_GRADE, showgrid=False,
                   tickangle=-45, tickfont=dict(size=9)),
        yaxis=dict(
            title=dict(text="Resultado R$", font=dict(size=10)),
            gridcolor=COR_GRADE,
            zerolinecolor=COR_GRADE,
            tickprefix="R$ ",
            tickformat=",.0f",
        ),
        yaxis2=dict(
            title=dict(text="Operações", font=dict(size=10)),
            overlaying="y",
            side="right",
            gridcolor="rgba(0,0,0,0)",
            showgrid=False,
            tickformat="d",
        ),
    ))
    return _to_html(fig)


def _grafico_consistencia(ops_por_dia: pd.DataFrame) -> str:
    """
    Barras de resultado por dia coloridas individualmente.
    Linha zero destacada.
    """
    if ops_por_dia.empty:
        return ""

    df_s = ops_por_dia.sort_values("data_dia")
    datas = df_s["data_dia"].apply(lambda d: d.strftime("%d/%m")).tolist()
    values = df_s["resultado_dia"].tolist()
    cores = [COR_POSITIVO if v >= 0 else COR_NEGATIVO for v in values]

    fig = go.Figure(go.Bar(
        x=datas,
        y=values,
        marker_color=cores,
        hovertemplate="<b>%{x}</b><br>Resultado: R$ %{y:,.2f}<extra></extra>",
    ))
    fig.add_hline(y=0, line_color=COR_GRADE, line_width=1)
    fig.update_layout(**_layout_base(
        height=240,
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


# ──────────────────────────────────────────────
# Gráficos — dashboard
# ──────────────────────────────────────────────

def _grafico_capital(df: pd.DataFrame) -> str:
    if df.empty:
        return ""

    df_sorted = df.sort_values("abertura")
    datas_str = df_sorted["abertura"].dt.strftime("%d/%m %H:%M").tolist()

    acumulado_array = np.array(df_sorted["total_acumulado"].astype(float))
    acumulado = acumulado_array.tolist()

    ymin = min(acumulado) * \
        1.15 if min(acumulado) < 0 else min(acumulado) * 0.85
    ymax = max(acumulado) * \
        1.15 if max(acumulado) > 0 else max(acumulado) * 0.85
    if ymin == ymax:
        ymin -= 100
        ymax += 100

    acumulado_pos = np.where(acumulado_array > 0, acumulado_array, 0).tolist()
    acumulado_neg = np.where(acumulado_array < 0, acumulado_array, 0).tolist()
    cor_linha = COR_POSITIVO if acumulado[-1] >= 0 else COR_NEGATIVO

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=datas_str, y=acumulado_pos, mode="lines",
                             fill="tozeroy", fillcolor="rgba(63,182,139,0.12)",
                             line=dict(width=0), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=datas_str, y=acumulado_neg, mode="lines",
                             fill="tozeroy", fillcolor="rgba(224,92,92,0.12)",
                             line=dict(width=0), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=datas_str, y=acumulado, mode="lines",
                             line=dict(color=cor_linha, width=2),
                             hovertemplate="<b>%{x}</b><br>Acumulado: R$ %{y:,.2f}<extra></extra>",
                             showlegend=False))
    fig.add_hline(y=0, line_color=COR_GRADE, line_width=1)
    fig.update_layout(**_layout_base(
        height=280,
        xaxis=dict(type="category", gridcolor=COR_GRADE, showgrid=False,
                   tickangle=-45, tickfont=dict(size=9)),
        yaxis=dict(gridcolor=COR_GRADE, zerolinecolor=COR_GRADE,
                   range=[ymin, ymax], tickprefix="R$ ", tickformat=",.0f"),
    ))
    return _to_html(fig)


def _grafico_horario(df: pd.DataFrame) -> str:
    if df.empty:
        return ""

    df2 = df.copy()
    df2["hora"] = df2["abertura"].dt.strftime("%H:00")
    agrupado = (df2.groupby("hora")["resultado_operacao"]
                .sum().reset_index().sort_values("hora"))
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
        yaxis=dict(gridcolor=COR_GRADE, zerolinecolor=COR_GRADE,
                   tickprefix="R$ ", tickformat=",.0f"),
    ))
    return _to_html(fig)


def _grafico_ativos(df: pd.DataFrame) -> str:
    if df.empty:
        return ""

    agrupado = (df.groupby("ativo_grupo")["resultado_operacao"]
                .sum().reset_index().sort_values("resultado_operacao"))
    cores = [COR_POSITIVO if v >= 0 else COR_NEGATIVO
             for v in agrupado["resultado_operacao"]]

    fig = go.Figure(go.Bar(
        x=agrupado["resultado_operacao"].astype(float).tolist(),
        y=agrupado["ativo_grupo"].tolist(),
        orientation="h", marker_color=cores,
        hovertemplate="<b>%{y}</b><br>Resultado: R$ %{x:,.2f}<extra></extra>",
    ))
    fig.update_layout(**_layout_base(
        height=280,
        xaxis=dict(gridcolor=COR_GRADE, zerolinecolor=COR_GRADE,
                   tickprefix="R$ ", tickformat=",.0f"),
        yaxis=dict(gridcolor=COR_GRADE, showgrid=False),
    ))
    return _to_html(fig)


def _grafico_heatmap(df: pd.DataFrame) -> str:
    if df.empty:
        return ""

    df2 = df.copy()
    df2["hora"] = df2["abertura"].dt.strftime("%H:00")
    df2["dia_semana"] = df2["abertura"].dt.strftime("%A")
    DIAS_PT = {"Monday": "Seg", "Tuesday": "Ter", "Wednesday": "Qua",
               "Thursday": "Qui", "Friday": "Sex"}
    df2["dia_pt"] = df2["dia_semana"].map(DIAS_PT).fillna(df2["dia_semana"])

    pivot = (df2.groupby(["dia_pt", "hora"])["resultado_operacao"]
             .sum().unstack(fill_value=0))
    ordem_dias = ["Seg", "Ter", "Qua", "Qui", "Sex"]
    pivot = pivot.reindex([d for d in ordem_dias if d in pivot.index])

    fig = go.Figure(go.Heatmap(
        z=pivot.values.tolist(),
        x=pivot.columns.tolist(),
        y=pivot.index.tolist(),
        zmid=0,
        colorscale=[[0.0, COR_NEGATIVO], [
            0.5, "#161b22"], [1.0, COR_POSITIVO]],
        hovertemplate="<b>%{y} %{x}</b><br>Resultado: R$ %{z:,.2f}<extra></extra>",
        showscale=True,
        colorbar=dict(tickfont=dict(size=9, color=COR_TEXTO),
                      tickprefix="R$", outlinewidth=0, len=0.8),
    ))
    fig.update_layout(**_layout_base(
        height=280,
        xaxis=dict(type="category", gridcolor=COR_GRADE, showgrid=False),
        yaxis=dict(gridcolor=COR_GRADE, showgrid=False),
    ))
    return _to_html(fig)


# ──────────────────────────────────────────────
# Gráficos — dia()
# ──────────────────────────────────────────────

def _grafico_capital_dia(df: pd.DataFrame) -> str:
    if df.empty:
        return ""

    df_s = df.sort_values("abertura").reset_index(drop=True)
    xs = df_s["abertura"].dt.strftime("%H:%M").tolist()

    ys_array = np.array(df_s["total_acumulado"].astype(float))
    ys = ys_array.tolist()

    ymin, ymax = min(ys), max(ys)
    margem = (ymax - ymin) * 0.18 if ymax != ymin else 100
    ymin -= margem
    ymax += margem

    ys_pos = np.where(ys_array > 0, ys_array, 0).tolist()
    ys_neg = np.where(ys_array < 0, ys_array, 0).tolist()
    cor_linha = COR_POSITIVO if ys[-1] >= 0 else COR_NEGATIVO

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=xs, y=ys_pos, mode="lines", fill="tozeroy",
                             fillcolor="rgba(63,182,139,0.12)", line=dict(width=0),
                             hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=xs, y=ys_neg, mode="lines", fill="tozeroy",
                             fillcolor="rgba(224,92,92,0.12)", line=dict(width=0),
                             hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines+markers",
                             line=dict(color=cor_linha, width=2),
                             marker=dict(size=5, color=cor_linha),
                             hovertemplate="<b>%{x}</b><br>Acumulado: R$ %{y:,.2f}<extra></extra>",
                             showlegend=False))
    fig.add_hline(y=0, line_color=COR_GRADE, line_width=1)
    fig.update_layout(**_layout_base(
        height=260,
        xaxis=dict(type="category", gridcolor=COR_GRADE, showgrid=False,
                   tickangle=-45, tickfont=dict(size=9)),
        yaxis=dict(gridcolor=COR_GRADE, zerolinecolor=COR_GRADE,
                   range=[ymin, ymax], tickprefix="R$ ", tickformat=",.0f"),
    ))
    return _to_html(fig)


def _grafico_horario_dia(df: pd.DataFrame) -> str:
    if df.empty:
        return ""

    df2 = df.copy()
    df2["hora"] = df2["abertura"].dt.strftime("%H:%M")
    agrupado = (df2.groupby("hora")["resultado_operacao"]
                .sum().reset_index().sort_values("hora"))
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
        yaxis=dict(gridcolor=COR_GRADE, zerolinecolor=COR_GRADE,
                   tickprefix="R$ ", tickformat=",.0f"),
    ))
    return _to_html(fig)


def _grafico_execucao(df: pd.DataFrame) -> str:
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
    fig.add_trace(go.Bar(x=resultados, y=labels, orientation="h",
                         marker_color=cores_barra, marker_opacity=0.85, name="Resultado",
                         hovertemplate="<b>%{y}</b><br>Resultado: R$ %{x:,.2f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=meps, y=labels, mode="markers",
                             marker=dict(symbol="triangle-right", size=10, color=COR_POSITIVO,
                                         line=dict(width=1, color="#0d1117")),
                             name="MEP",
                             hovertemplate="<b>%{y}</b><br>MEP: R$ %{x:,.2f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=mens, y=labels, mode="markers",
                             marker=dict(symbol="triangle-left", size=10, color=COR_NEGATIVO,
                                         line=dict(width=1, color="#0d1117")),
                             name="MEN",
                             hovertemplate="<b>%{y}</b><br>MEN: R$ %{x:,.2f}<extra></extra>"))

    altura = max(260, 80 + len(labels) * 38)
    fig.update_layout(**_layout_base(
        height=altura, showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, font=dict(size=10, color=COR_TEXTO)),
        xaxis=dict(gridcolor=COR_GRADE, zerolinecolor=COR_GRADE,
                   tickprefix="R$ ", tickformat=",.0f"),
        yaxis=dict(gridcolor=COR_GRADE, showgrid=False),
        barmode="overlay",
    ))
    return _to_html(fig)


# ──────────────────────────────────────────────
# Views
# ──────────────────────────────────────────────

def dashboard(request):
    data_inicio, data_fim, qs = _filtrar_operacoes(request)
    df = _qs_to_df(qs)

    if df.empty:
        resultado_total = total_operacoes = total_wins = total_losses = 0
        win_rate = melhor_op = pior_op = 0.0
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

    metricas_av = _calcular_metricas_avancadas(df)

    context = {
        "data_inicio": data_inicio,
        "data_fim":    data_fim,
        "resultado_total":  resultado_total,
        "total_operacoes":  total_operacoes,
        "total_wins":       total_wins,
        "total_losses":     total_losses,
        "win_rate":         round(win_rate, 1),
        "melhor_op":        melhor_op,
        "pior_op":          pior_op,
        "total_sessoes":    total_sessoes,
        "expectativa_matematica": metricas_av["expectativa_matematica"],
        "payoff_ratio":           metricas_av["payoff_ratio"],
        "gain_medio":             metricas_av["gain_medio"],
        "loss_medio":             metricas_av["loss_medio"],
        "grafico_capital": _grafico_capital(df),
        "grafico_horario": _grafico_horario(df),
        "grafico_ativos":  _grafico_ativos(df),
        "grafico_heatmap": _grafico_heatmap(df),
    }
    return render(request, "trades/dashboard.html", context)


def operacoes(request):
    data_inicio, data_fim, qs = _filtrar_operacoes(request)
    instrumento = request.GET.get("instrumento", "").strip()
    por_pagina = request.GET.get("por_pagina",  "10").strip()

    OPCOES_POR_PAGINA = [10, 20, 50, 100]
    try:
        por_pagina = int(por_pagina)
        if por_pagina not in OPCOES_POR_PAGINA:
            por_pagina = 10
    except (ValueError, TypeError):
        por_pagina = 10

    if instrumento:
        qs = qs.filter(ativo__startswith=instrumento)

    todos_ativos = Operacao.objects.values_list(
        "ativo", flat=True).distinct().order_by("ativo")
    ativos_agrupados = sorted({_agrupar_ativo(a) for a in todos_ativos})

    campos = [
        "id", "ativo", "lado", "abertura", "fechamento",
        "tempo_operacao", "qtd_compra", "qtd_venda",
        "preco_compra", "preco_venda",
        "resultado_operacao", "total_acumulado",
    ]
    registros = list(qs.order_by("-abertura").values(*campos))

    total_operacoes = len(registros)
    total_res = total_wins = total_losses = 0.0
    for r in registros:
        res = float(r["resultado_operacao"] or 0)
        total_res += res
        if res > 0:
            total_wins += 1
        else:
            total_losses += 1
    win_rate = (total_wins / total_operacoes * 100) if total_operacoes else 0.0

    # Acumulado cronológico
    registros_cronologicos = list(reversed(registros))
    acumulado_periodo = 0.0
    registros_conv = []
    for r in registros_cronologicos:
        abertura_utc = r["abertura"]
        abertura_local = (abertura_utc.astimezone(TZ_BR)
                          if abertura_utc and hasattr(abertura_utc, "astimezone")
                          else abertura_utc)
        acumulado_periodo += float(r["resultado_operacao"] or 0)
        registros_conv.append({
            **r,
            "abertura_local": abertura_local,
            "total_acumulado": round(acumulado_periodo, 2),
        })
    registros_conv = list(reversed(registros_conv))

    # ── Journal: enriquecer cada registro com dados do journal ──
    todos_ids = [r["id"] for r in registros_conv]
    journals_map = {
        j.operacao_id: j
        for j in JournalOperacao.objects.filter(operacao_id__in=todos_ids)
    }
    for r in registros_conv:
        j = journals_map.get(r["id"])
        r["has_journal"] = j is not None
        r["journal_setup"] = j.setup if j else ""
        r["journal_tags"] = j.tags if j else ""
        r["journal_emocao"] = j.emocao if j else ""
        r["journal_q_entrada"] = j.qualidade_entrada if j else ""
        r["journal_q_saida"] = j.qualidade_saida if j else ""
        r["journal_anotacao"] = j.anotacao if j else ""

    # ── Setups existentes para autocomplete ──
    setups_existentes = list(
        JournalOperacao.objects.exclude(setup="")
        .values_list("setup", flat=True).distinct().order_by("setup")
    )

    # Paginação
    paginator = Paginator(registros_conv, por_pagina)
    pagina_num = request.GET.get("pagina", 1)
    try:
        pagina_num = int(pagina_num)
    except (ValueError, TypeError):
        pagina_num = 1
    pagina_obj = paginator.get_page(pagina_num)

    num_pages = paginator.num_pages
    pagina_atual = pagina_obj.number
    inicio = max(1, pagina_atual - 2)
    fim = min(num_pages, pagina_atual + 2)
    if fim - inicio < 4:
        fim = min(num_pages, inicio + 4) if inicio == 1 else fim
        inicio = max(1, fim - 4) if inicio != 1 else inicio
    intervalo_paginas = range(inicio, fim + 1)

    get_sem_pagina = request.GET.copy()
    get_sem_pagina.pop("pagina", None)
    query_string = get_sem_pagina.urlencode()

    context = {
        "data_inicio":        data_inicio,
        "data_fim":           data_fim,
        "instrumento":        instrumento,
        "ativos_disponiveis": ativos_agrupados,
        "operacoes":          pagina_obj,
        "pagina_obj":         pagina_obj,
        "intervalo_paginas":  intervalo_paginas,
        "query_string":       query_string,
        "total_operacoes":    total_operacoes,
        "resultado_total":    round(total_res, 2),
        "total_wins":         int(total_wins),
        "total_losses":       int(total_losses),
        "win_rate":           round(win_rate, 1),
        "por_pagina":         por_pagina,
        "opcoes_por_pagina":  OPCOES_POR_PAGINA,
        # Journal
        "setups_existentes":  setups_existentes,
    }
    return render(request, "trades/operacoes.html", context)

def importar(request):
    resultado = None
    erro = None

    if request.method == "POST":
        acao = request.POST.get("acao", "importar")

        if acao == "excluir":
            data_excluir = request.POST.get("data_excluir",  "").strip()
            ativo_excluir = request.POST.get("ativo_excluir", "").strip()
            confirmar = request.POST.get("confirmar_exclusao", "")

            if not data_excluir:
                messages.error(request, "Selecione uma data para excluir.")
            elif confirmar != "1":
                messages.warning(
                    request, "Marque a caixa de confirmação antes de excluir.")
            else:
                qs_del = Operacao.objects.filter(abertura__date=data_excluir)
                if ativo_excluir and ativo_excluir != "todos":
                    qs_del = qs_del.filter(ativo__startswith=ativo_excluir)

                total_ops = qs_del.count()
                if total_ops == 0:
                    messages.warning(request, "Nenhuma operação encontrada.")
                else:
                    qs_del.delete()
                    SessaoOperacao.objects.filter(
                        operacoes__isnull=True).delete()
                    ImportacaoArquivo.objects.filter(
                        operacoes__isnull=True).delete()
                    descricao = data_excluir
                    if ativo_excluir and ativo_excluir != "todos":
                        descricao += f" · {ativo_excluir}"
                    messages.success(
                        request,
                        f"{total_ops} operaç{'ão' if total_ops == 1 else 'ões'} "
                        f"excluída{'s' if total_ops > 1 else ''} ({descricao})."
                    )
            return redirect("trades:importar")

        arquivo = request.FILES.get("arquivo")
        if not arquivo:
            erro = "Nenhum arquivo enviado."
        else:
            try:
                importacao = importar_csv(arquivo)
                resultado = importacao
                messages.success(request,
                                 f"{importacao.total_operacoes} operações importadas com sucesso.")
            except Exception as exc:  # noqa: BLE001
                erro = str(exc)
                messages.error(request, erro)

    importacoes = ImportacaoArquivo.objects.order_by("-importado_em")[:10]

    dias_no_banco = Operacao.objects.dates("abertura", "day", order="DESC")
    dias_exclusao = [d.strftime("%Y-%m-%d") for d in dias_no_banco]

    ativos_por_dia: dict[str, list[str]] = {}
    for row in (Operacao.objects.values("abertura__date", "ativo")
                .distinct().order_by("abertura__date", "ativo")):
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
        "ativos_por_dia": json.dumps(ativos_por_dia),
    }
    return render(request, "trades/importar.html", context)


def dia(request):
    dias_disponiveis = Operacao.objects.dates("abertura", "day", order="DESC")
    dias_str = [d.strftime("%Y-%m-%d") for d in dias_disponiveis]

    if not dias_str:
        return render(request, "trades/dia.html", {"sem_dados": True})

    data_sel = request.GET.get("data", dias_str[0]).strip()
    if data_sel not in dias_str:
        data_sel = dias_str[0]

    campos = [
        "id", "ativo", "lado", "abertura", "fechamento",
        "tempo_operacao", "qtd_compra", "qtd_venda",
        "preco_compra", "preco_venda", "preco_medio",
        "resultado_operacao", "total_acumulado",
        "mep", "men", "ganho_maximo", "perda_maxima",
    ]
    qs = (Operacao.objects.filter(abertura__date=data_sel)
          .order_by("abertura").values(*campos))
    registros = list(qs)

    if not registros:
        return render(request, "trades/dia.html", {
            "sem_dados": False, "dias_disponiveis": dias_str,
            "data_sel": data_sel, "sem_ops": True,
        })

    df = pd.DataFrame(registros)
    df["abertura"] = pd.to_datetime(
        df["abertura"], utc=True).dt.tz_convert(TZ_BR)
    df["resultado_operacao"] = df["resultado_operacao"].astype(float)
    df = df.sort_values("abertura").reset_index(drop=True)
    df["total_acumulado"] = df["resultado_operacao"].cumsum()
    df["mep"] = df["mep"].astype(float)
    df["men"] = df["men"].astype(float)

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

    df["fechamento_local"] = pd.to_datetime(
        df["fechamento"], utc=True).dt.tz_convert(TZ_BR)
    df["duracao_min"] = (
        (df["fechamento_local"] - df["abertura"]).dt.total_seconds() / 60)

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
        "sem_dados": False, "sem_ops": False,
        "dias_disponiveis": dias_str, "data_sel": data_sel,
        "resultado_total": round(resultado, 2),
        "win_rate":        round(win_rate, 1),
        "total_ops":       total_ops,
        "fator_lucro":     round(fator_lucro, 2) if fator_lucro else None,
        "drawdown_max":    round(drawdown_max, 2),
        "exposicao_neg":   round(exposicao_neg, 2),
        "maior_gain":      round(maior_gain, 2),
        "maior_gain_ativo": maior_gain_ativo,
        "maior_gain_hora":  maior_gain_hora,
        "maior_loss":      round(maior_loss, 2),
        "maior_loss_ativo": maior_loss_ativo,
        "maior_loss_hora":  maior_loss_hora,
        "tempo_medio_win":  tempo_medio_win,
        "tempo_medio_loss": tempo_medio_loss,
        "razao_tempo":      razao,
        "total_wins":       total_wins,
        "total_losses":     total_losses,
        "payoff_ratio_dia":  metricas_av_dia["payoff_ratio"],
        "gain_medio_dia":    metricas_av_dia["gain_medio"],
        "loss_medio_dia":    metricas_av_dia["loss_medio"],
        "grafico_capital":  _grafico_capital_dia(df),
        "grafico_horario":  _grafico_horario_dia(df),
        "grafico_execucao": _grafico_execucao(df),
        "operacoes":        tabela,
    }
    return render(request, "trades/dia.html", context)


def comportamental(request):
    """
    Página de indicadores comportamentais.
    Suporta filtro de período (data_inicio / data_fim).
    Consome ParametrosTrader.carregar() para os limiares configuráveis.
    """
    data_inicio, data_fim, qs = _filtrar_operacoes(request)
    params = ParametrosTrader.carregar()

    # Campos necessários para os indicadores comportamentais
    campos = [
        "id", "ativo", "abertura", "fechamento",
        "resultado_operacao", "mep", "men",
        "sessao__data_sessao",
    ]
    registros = list(qs.order_by("abertura").values(*campos))

    if not registros:
        return render(request, "trades/comportamental.html", {
            "sem_dados":    True,
            "data_inicio":  data_inicio,
            "data_fim":     data_fim,
            "limiar_revenge":     params.tempo_minimo_entre_trades,
            "limiar_overtrading": params.max_operacoes_dia,
        })

    df = pd.DataFrame(registros)
    df["abertura"] = pd.to_datetime(
        df["abertura"], utc=True).dt.tz_convert(TZ_BR)
    df["resultado_operacao"] = df["resultado_operacao"].astype(float)
    df["mep"] = df["mep"].astype(float)
    df["men"] = df["men"].astype(float)

    indicadores = _calcular_comportamental(df, params)

    context = {
        "data_inicio": data_inicio,
        "data_fim":    data_fim,
        **indicadores,
    }
    return render(request, "trades/comportamental.html", context)


# ─── JOURNAL ──────────────────────────────────────────────────────────────────

def journal(request):
    """Página principal do journal com listagem e métricas por setup."""
    import pytz
    from django.db.models import Avg, Count, Sum

    tz_sp = pytz.timezone('America/Sao_Paulo')

    # Filtros
    setup_filtro = request.GET.get('setup', '')
    tag_filtro = request.GET.get('tag', '')
    emocao_filtro = request.GET.get('emocao', '')
    data_ini = request.GET.get('data_ini', '')
    data_fim = request.GET.get('data_fim', '')

    qs = JournalOperacao.objects.select_related('operacao').all()

    if setup_filtro:
        qs = qs.filter(setup__iexact=setup_filtro)
    if emocao_filtro:
        qs = qs.filter(emocao=emocao_filtro)
    if tag_filtro:
        qs = qs.filter(tags__icontains=tag_filtro)
    if data_ini:
        qs = qs.filter(operacao__abertura__date__gte=data_ini)
    if data_fim:
        qs = qs.filter(operacao__abertura__date__lte=data_fim)

    # Converter datas para exibição
    journals = []
    for j in qs:
        abertura_sp = j.operacao.abertura.astimezone(
            tz_sp) if j.operacao.abertura else None
        journals.append({
            'id':               j.pk,
            'op_id':            j.operacao.pk,
            'ativo':            j.operacao.ativo,
            'abertura':         abertura_sp,
            'resultado':        j.operacao.resultado_operacao,
            'is_win':           j.operacao.is_win,
            'setup':            j.setup,
            'tags_lista':       j.tags_lista(),
            'emocao':           j.get_emocao_display(),
            'emocao_slug':      j.emocao,
            'qualidade_entrada': j.qualidade_entrada,
            'qualidade_saida':  j.qualidade_saida,
            'anotacao':         j.anotacao,
        })

    # Métricas por setup
    setups_raw = (
        JournalOperacao.objects
        .exclude(setup='')
        .values('setup')
        .annotate(
            total=Count('pk'),
            resultado_total=Sum('operacao__resultado_operacao'),
            q_entrada_media=Avg('qualidade_entrada'),
            q_saida_media=Avg('qualidade_saida'),
        )
        .order_by('-resultado_total')
    )

    metricas_setup = []
    for s in setups_raw:
        ops_setup = JournalOperacao.objects.filter(setup__iexact=s['setup'])
        wins = sum(1 for j in ops_setup if j.operacao.resultado_operacao > 0)
        total = s['total']
        win_rate = (wins / total * 100) if total else 0

        # Expectativa matemática simplificada
        resultados = [float(j.operacao.resultado_operacao) for j in ops_setup]
        media = sum(resultados) / len(resultados) if resultados else 0

        metricas_setup.append({
            'setup':          s['setup'],
            'total':          total,
            'resultado_total': s['resultado_total'],
            'win_rate':       round(win_rate, 1),
            'media_resultado': round(media, 2),
            'q_entrada_media': round(s['q_entrada_media'] or 0, 1),
            'q_saida_media':  round(s['q_saida_media'] or 0, 1),
        })

    # Opções para filtros
    setups_disponiveis = (
        JournalOperacao.objects.exclude(setup='')
        .values_list('setup', flat=True).distinct().order_by('setup')
    )

    context = {
        'journals':           journals,
        'metricas_setup':     metricas_setup,
        'setups_disponiveis': setups_disponiveis,
        'emocao_choices':     JournalOperacao.EMOCAO_CHOICES,
        'filtros': {
            'setup':    setup_filtro,
            'tag':      tag_filtro,
            'emocao':   emocao_filtro,
            'data_ini': data_ini,
            'data_fim': data_fim,
        },
        'total_anotacoes': qs.count(),
    }
    return render(request, 'trades/journal.html', context)


def salvar_journal(request, op_id):
    """Salva ou atualiza o journal de uma operação via POST."""
    import json
    from django.views.decorators.http import require_POST

    if request.method != 'POST':
        from django.http import JsonResponse
        return JsonResponse({'ok': False, 'erro': 'Método não permitido'}, status=405)

    operacao = get_object_or_404(Operacao, pk=op_id)
    journal_obj, _ = JournalOperacao.objects.get_or_create(operacao=operacao)

    journal_obj.setup = request.POST.get('setup', '').strip()
    journal_obj.tags = request.POST.get('tags', '').strip()
    journal_obj.emocao = request.POST.get('emocao', '')
    journal_obj.anotacao = request.POST.get('anotacao', '').strip()

    q_entrada = request.POST.get('qualidade_entrada', '')
    q_saida = request.POST.get('qualidade_saida', '')
    journal_obj.qualidade_entrada = int(
        q_entrada) if q_entrada.isdigit() else None
    journal_obj.qualidade_saida = int(q_saida) if q_saida.isdigit() else None

    journal_obj.save()

    # Resposta JSON para o drawer fechar sem reload de página
    from django.http import JsonResponse
    return JsonResponse({
        'ok':      True,
        'op_id':   op_id,
        'setup':   journal_obj.setup,
        'has_journal': True,
    })
