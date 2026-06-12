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

from .models import (ImportacaoArquivo, Operacao,
                     ParametrosTrader, SessaoOperacao,
                     JournalOperacao, AnotacaoDia,
                     )

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
        "sessao__data_sessao", "resultado_operacao_pontos",
    ]
    registros = list(qs.values(*campos))
    if not registros:
        return pd.DataFrame()
    df = pd.DataFrame(registros)
    df["abertura"] = pd.to_datetime(
        df["abertura"], utc=True).dt.tz_convert(TZ_BR)
    df["ativo_grupo"] = df["ativo"].apply(_agrupar_ativo)
    return df


def _drawdown_maximo(df: pd.DataFrame) -> float:
    """
    Calcula o drawdown máximo do período.
    Retorna o valor absoluto do maior recuo a partir do pico.
    """
    if df.empty:
        return 0.0
    df_ord = df.sort_values("abertura")
    acumulado = df_ord["resultado_operacao"].astype(float).cumsum()
    pico = acumulado.cummax()
    drawdown = pico - acumulado
    return float(drawdown.max())


def _grafico_drawdown(df: pd.DataFrame) -> str:
    """
    Gera gráfico de drawdown ponto a ponto abaixo da curva de capital.
    Retorna HTML do Plotly ou string vazia se df vazio.
    """
    if df.empty:
        return ''

    df_ord = df.sort_values('abertura').copy()
    df_ord['abertura_str'] = df_ord['abertura'].dt.strftime('%d/%m %H:%M')
    acumulado = df_ord['resultado_operacao'].astype(float).cumsum()
    pico = acumulado.cummax()
    drawdown = acumulado - pico  # sempre <= 0

    drawdown_max_val = float(drawdown.min())  # valor mais negativo

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df_ord['abertura_str'].tolist(),
        y=drawdown.tolist(),
        mode='lines',
        fill='tozeroy',
        fillcolor='rgba(224, 92, 92, 0.25)',
        line=dict(color='#e05c5c', width=1.5),
        hovertemplate='%{x}<br>Drawdown: R$ %{y:,.2f}<extra></extra>',
    ))

    # Anotação com o valor máximo de drawdown
    if drawdown_max_val < 0:
        idx_min = drawdown.idxmin()
        fig.add_annotation(
            x=df_ord.loc[idx_min, 'abertura_str'],
            y=drawdown_max_val,
            text=f'Máx: R$ {drawdown_max_val:,.2f}',
            showarrow=True,
            arrowhead=2,
            arrowcolor='#e05c5c',
            font=dict(color='#e05c5c', size=11),
            bgcolor='#161b22',
            bordercolor='#e05c5c',
            borderwidth=1,
            ay=-30,
        )

    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#b8c4ce', family='monospace', size=11),
        margin=dict(l=10, r=10, t=8, b=8),
        height=160,
        xaxis=dict(
            type='category',
            showgrid=False,
            showticklabels=False,
            zeroline=False,
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='#21262d',
            tickprefix='R$ ',
            tickformat=',.0f',
            zeroline=True,
            zerolinecolor='#444c56',
            zerolinewidth=1,
        ),
        showlegend=False,
    )

    return fig.to_html(full_html=False, include_plotlyjs=False)

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

    # Avaliação relativa: % de episódios sobre o total de operações do período
    # (divide por total-1 pois a primeira op nunca pode ser revenge)
    total_ops_periodo = len(df)
    revenge_pct = (
        round(revenge_total / (total_ops_periodo - 1) * 100, 1)
        if total_ops_periodo > 1 else 0.0
    )

    if revenge_pct == 0:
        revenge_avaliacao = "Nenhum"
        revenge_cor = "success"
    elif revenge_pct < 5:
        revenge_avaliacao = "Baixo"
        revenge_cor = "success"
    elif revenge_pct < 15:
        revenge_avaliacao = "Moderado"
        revenge_cor = "warning"
    else:
        revenge_avaliacao = "Alto"
        revenge_cor = "danger"

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

    # ── 6. Correlação Overtrading × Revenge ───────────────────────
    # Para cada dia, conta quantos episódios de revenge ocorreram
    revenge_por_dia: dict = {}
    for r_op in revenge_ops:
        # abertura está em formato "dd/mm HH:MM" — precisamos só da data
        # mas como já agrupamos ops_por_dia por data, reconstruímos do df
        pass

    # Reconstrói contagem de revenge por dia a partir do df já ordenado
    df_revenge_flags = pd.Series([False] * len(df), index=df.index)
    for i in range(1, len(df)):
        op_anterior = df.iloc[i - 1]
        op_atual = df.iloc[i]
        if op_anterior["resultado_operacao"] >= 0:
            continue
        diff_min = (op_atual["abertura"] -
                    op_anterior["abertura"]).total_seconds() / 60
        if diff_min < limiar_min:
            df_revenge_flags.iloc[i] = True

    df["is_revenge"] = df_revenge_flags
    df["data_dia"] = df["abertura"].dt.date  # pode já existir — sem problema

    revenge_count_dia = df.groupby(
        "data_dia")["is_revenge"].sum().rename("n_revenge")
    ops_por_dia = ops_por_dia.join(
        revenge_count_dia, on="data_dia", how="left")
    ops_por_dia["n_revenge"] = ops_por_dia["n_revenge"].fillna(0).astype(int)
    ops_por_dia["tem_revenge"] = ops_por_dia["n_revenge"] > 0

    # Correlação de Pearson entre qtd_ops e n_revenge (mínimo 3 dias)
    corr_overtrade_revenge = None
    if len(ops_por_dia) >= 3:
        try:
            corr_val = float(ops_por_dia["total_ops"].corr(
                ops_por_dia["n_revenge"]))
            if not (corr_val != corr_val):  # nan check
                corr_overtrade_revenge = round(corr_val, 3)
        except Exception:
            pass

    # % de dias NORMAIS (sem overtrading) que tiveram revenge
    dias_normais = ops_por_dia[ops_por_dia["total_ops"] <= limiar_ops]
    dias_overtrade = ops_por_dia[ops_por_dia["total_ops"] > limiar_ops]

    revenge_pct_dias_normais = (
        round(dias_normais["tem_revenge"].sum() / len(dias_normais) * 100, 1)
        if len(dias_normais) > 0 else None
    )
    revenge_pct_dias_overtrade = (
        round(dias_overtrade["tem_revenge"].sum() /
              len(dias_overtrade) * 100, 1)
        if len(dias_overtrade) > 0 else None
    )

    # Interpretação da correlação
    if corr_overtrade_revenge is None:
        corr_interpretacao = "dados insuficientes"
    elif corr_overtrade_revenge >= 0.5:
        corr_interpretacao = "forte — overtrading eleva o risco de revenge"
    elif corr_overtrade_revenge >= 0.2:
        corr_interpretacao = "moderada — alguma relação entre volume e impulsividade"
    elif corr_overtrade_revenge >= -0.2:
        corr_interpretacao = "fraca — comportamentos pouco relacionados"
    else:
        corr_interpretacao = "negativa — sem relação direta"

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
        "revenge_pct":        revenge_pct,
        "revenge_avaliacao":  revenge_avaliacao,
        "revenge_cor":        revenge_cor,
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
        # 6. Correlação Overtrading × Revenge
        "corr_overtrade_revenge":       corr_overtrade_revenge,
        "corr_interpretacao":           corr_interpretacao,
        "revenge_pct_dias_normais":     revenge_pct_dias_normais,
        "revenge_pct_dias_overtrade":   revenge_pct_dias_overtrade,
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

    agrupado = (
        df.groupby("ativo_grupo")
        .agg(
            resultado_operacao=("resultado_operacao", "sum"),
            n_ops=("resultado_operacao", "count"),
        )
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
        text=None,          
        texttemplate=None,
        customdata=agrupado["n_ops"].tolist(),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Resultado: R$ %{x:,.2f}<br>"
            "Operações: %{customdata}<extra></extra>"
        ),
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
# Gráficos — analise_setup()
# ──────────────────────────────────────────────

def _grafico_analise_setup(metricas: list) -> str:
    """
    Barras horizontais de resultado total por setup.
    Exclui o grupo '(sem setup)' se existir outros grupos.
    """
    dados = [m for m in metricas if not m.get("sem_setup")]
    if not dados:
        dados = metricas  # fallback: mostra tudo
    if not dados:
        return ""

    nomes = [m["nome"] for m in dados]
    resultados = [m["resultado_total"] for m in dados]
    win_rates = [m["win_rate"] for m in dados]
    cores = [COR_POSITIVO if r >= 0 else COR_NEGATIVO for r in resultados]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=resultados,
        y=nomes,
        orientation="h",
        marker_color=cores,
        text=[f"R$ {r:,.0f}" for r in resultados],
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>Resultado: R$ %{x:,.2f}<extra></extra>",
    ))
    fig.update_layout(**_layout_base(
        height=max(220, 60 + len(dados) * 44),
        xaxis=dict(gridcolor=COR_GRADE, zerolinecolor=COR_GRADE,
                   tickprefix="R$ ", tickformat=",.0f"),
        yaxis=dict(gridcolor=COR_GRADE, showgrid=False),
    ))
    return _to_html(fig)


def _grafico_analise_tag(metricas: list) -> str:
    """
    Barras horizontais de resultado total por tag.
    Mostra no máximo 15 tags ordenadas por resultado.
    """
    dados = metricas[:15]
    if not dados:
        return ""

    nomes = [m["nome"] for m in dados]
    resultados = [m["resultado_total"] for m in dados]
    cores = [COR_POSITIVO if r >= 0 else COR_NEGATIVO for r in resultados]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=resultados,
        y=nomes,
        orientation="h",
        marker_color=cores,
        text=[f"R$ {r:,.0f}" for r in resultados],
        textposition="outside",
        hovertemplate="<b>#%{y}</b><br>Resultado: R$ %{x:,.2f}<extra></extra>",
    ))
    fig.update_layout(**_layout_base(
        height=max(220, 60 + len(dados) * 44),
        xaxis=dict(gridcolor=COR_GRADE, zerolinecolor=COR_GRADE,
                   tickprefix="R$ ", tickformat=",.0f"),
        yaxis=dict(gridcolor=COR_GRADE, showgrid=False),
    ))
    return _to_html(fig)


# ──────────────────────────────────────────────
# Gráficos — comparativo()
# ──────────────────────────────────────────────

def _grafico_comparativo_curvas(df1, df2, p1_ini, p1_fim, p2_ini, p2_fim) -> str:
    """
    Curvas de capital dos dois períodos sobrepostas num mesmo gráfico.
    Eixo X normalizado como % do total de operações de cada período (0–100).
    """
    if df1.empty and df2.empty:
        return ""

    fig = go.Figure()

    def _add_curva(df, label, cor, cor_fill):
        if df.empty:
            return
        acum = df["resultado_operacao"].cumsum().tolist()
        # Normaliza X como índice percentual (0 a 100) para comparar períodos
        n = len(acum)
        xs = [round(i / (n - 1) * 100, 1) if n > 1 else 0 for i in range(n)]
        fig.add_trace(go.Scatter(
            x=xs, y=acum,
            mode="lines",
            name=label,
            line=dict(color=cor, width=2),
            fill="tozeroy",
            fillcolor=cor_fill,
            hovertemplate=f"<b>{label}</b><br>Op: %{{x:.0f}}%<br>Acum: R$ %{{y:,.2f}}<extra></extra>",
        ))

    label1 = f"P1: {p1_ini} → {p1_fim}"
    label2 = f"P2: {p2_ini} → {p2_fim}"
    _add_curva(df1, label1, COR_POSITIVO, "rgba(63,182,139,0.10)")
    _add_curva(df2, label2, COR_AZUL,     "rgba(56,139,253,0.10)")

    fig.add_hline(y=0, line_color=COR_GRADE, line_width=1)
    fig.update_layout(**_layout_base(
        height=300,
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="right", x=1,
            font=dict(size=11, color=COR_TEXTO),
        ),
        xaxis=dict(
            gridcolor=COR_GRADE, showgrid=True,
            ticksuffix="%", title=dict(text="Progresso das operações", font=dict(size=10)),
        ),
        yaxis=dict(
            gridcolor=COR_GRADE, zerolinecolor=COR_GRADE,
            tickprefix="R$ ", tickformat=",.0f",
        ),
    ))
    return _to_html(fig)


def _grafico_comparativo_barras(m1, m2) -> str:
    """
    Barras agrupadas das principais métricas dos dois períodos.
    """
    if not m1 or not m2:
        return ""

    metricas = [
        ("Win Rate (%)",  m1["win_rate"],  m2["win_rate"]),
        ("Resultado (R$)", m1["resultado"], m2["resultado"]),
        # inverte sinal p/ visual
        ("Drawdown (R$)", -m1["drawdown"], -m2["drawdown"]),
    ]
    if m1.get("em") is not None and m2.get("em") is not None:
        metricas.append(("EM (R$)", m1["em"], m2["em"]))
    if m1.get("payoff") is not None and m2.get("payoff") is not None:
        metricas.append(("Payoff", m1["payoff"], m2["payoff"]))

    labels = [m[0] for m in metricas]
    vals1 = [m[1] for m in metricas]
    vals2 = [m[2] for m in metricas]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Período 1", x=labels, y=vals1,
        marker_color=COR_POSITIVO, marker_opacity=0.85,
        hovertemplate="<b>%{x}</b><br>P1: %{y:,.2f}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name="Período 2", x=labels, y=vals2,
        marker_color=COR_AZUL, marker_opacity=0.85,
        hovertemplate="<b>%{x}</b><br>P2: %{y:,.2f}<extra></extra>",
    ))
    fig.update_layout(**_layout_base(
        height=280,
        barmode="group",
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="right", x=1,
            font=dict(size=11, color=COR_TEXTO),
        ),
        xaxis=dict(type="category", gridcolor=COR_GRADE, showgrid=False),
        yaxis=dict(gridcolor=COR_GRADE, zerolinecolor=COR_GRADE),
    ))
    return _to_html(fig)


# ──────────────────────────────────────────────
# Views
# ──────────────────────────────────────────────

def dashboard(request):
    data_inicio, data_fim, qs = _filtrar_operacoes(request)
    df = _qs_to_df(qs)

    params = ParametrosTrader.carregar()
    capital_inicial = float(params.capital_inicial)

    if df.empty:
        resultado_total = total_operacoes = total_wins = total_losses = 0
        win_rate = melhor_op = pior_op = 0.0
        total_sessoes = 0
        drawdown_max = 0.0
        resultado_pontos = 0.0
        grafico_drawdown = ''
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
        drawdown_max = _drawdown_maximo(df)
        resultado_pontos = float(df["resultado_operacao_pontos"].sum())
        grafico_drawdown = _grafico_drawdown(df)

    # Retorno % e Drawdown % sobre capital
    if capital_inicial > 0:
        retorno_pct = round(resultado_total / capital_inicial * 100, 2)
        drawdown_pct = round(drawdown_max / capital_inicial * 100, 2)
    else:
        retorno_pct = None
        drawdown_pct = None

    metricas_av = _calcular_metricas_avancadas(df)

    context = {
        "data_inicio":    data_inicio,
        "data_fim":       data_fim,
        "resultado_total":  resultado_total,
        "total_operacoes":  total_operacoes,
        "total_wins":       total_wins,
        "total_losses":     total_losses,
        "win_rate":         round(win_rate, 1),
        "melhor_op":        melhor_op,
        "pior_op":          pior_op,
        "total_sessoes":    total_sessoes,
        # Passo 2
        "capital_inicial":  capital_inicial,
        "retorno_pct":      retorno_pct,
        "drawdown_max":     round(drawdown_max, 2),
        "drawdown_pct":     drawdown_pct,
        "resultado_pontos": round(resultado_pontos, 0) if not df.empty else 0,
        # Métricas avançadas
        "expectativa_matematica": metricas_av["expectativa_matematica"],
        "payoff_ratio":           metricas_av["payoff_ratio"],
        "gain_medio":             metricas_av["gain_medio"],
        "loss_medio":             metricas_av["loss_medio"],
        # Gráficos
        "grafico_capital":  _grafico_capital(df),
        "grafico_horario":  _grafico_horario(df),
        "grafico_ativos":   _grafico_ativos(df),
        "grafico_heatmap":  _grafico_heatmap(df),
        # Passo 7
        "grafico_drawdown": grafico_drawdown,
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
        "resultado_operacao_pontos",
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
        r["pk"] = r["id"]
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
                importacao = importar_csv(arquivo, arquivo.name)
                if importacao['sucesso']:
                    resultado = importacao
                    messages.success(request,
                                     f"{importacao['total_operacoes']} operações importadas com sucesso.")
                else:
                    erro = importacao['erro']
                    messages.error(request, erro)
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

    # --- Salvar Anotação do Dia via POST ---
    if request.method == 'POST':
        data_post = request.POST.get('data_sessao', '').strip()
        if data_post:
            anotacao, _ = AnotacaoDia.objects.get_or_create(
                data_sessao=data_post)
            anotacao.contexto_mercado = request.POST.get(
                'contexto_mercado', '').strip()
            anotacao.estado_emocional = request.POST.get(
                'estado_emocional', '').strip()
            score_raw = request.POST.get('score_dia', '').strip()
            anotacao.score_dia = int(score_raw) if score_raw.isdigit(
            ) and 1 <= int(score_raw) <= 10 else None
            anotacao.observacao = request.POST.get('observacao', '').strip()
            anotacao.save()
        return redirect(f"{request.path}?data={data_post}")

    data_sel = request.GET.get("data", dias_str[0]).strip()
    if data_sel not in dias_str:
        data_sel = dias_str[0]

    campos = [
        "id", "ativo", "lado", "abertura", "fechamento",
        "tempo_operacao", "qtd_compra", "qtd_venda",
        "preco_compra", "preco_venda", "preco_medio",
        "resultado_operacao", "total_acumulado",
        "mep", "men", "ganho_maximo", "perda_maxima",
        "resultado_operacao_pontos",
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
    df["resultado_operacao_pontos"] = df["resultado_operacao_pontos"].astype(
        float)

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
            "ativo":                     row["ativo"],
            "lado":                      row["lado"],
            "abertura_local":            row["abertura"],
            "qtd_compra":                row["qtd_compra"],
            "preco_compra":              row["preco_compra"],
            "preco_venda":               row["preco_venda"],
            "mep":                       row["mep"],
            "men":                       row["men"],
            "resultado_operacao":        row["resultado_operacao"],
            "resultado_operacao_pontos": row["resultado_operacao_pontos"],
            "tempo_operacao":            row["tempo_operacao"],
            "total_acumulado":           row["total_acumulado"],
        })

    # --- Anotação do Dia ---
    anotacao_dia = AnotacaoDia.objects.filter(data_sessao=data_sel).first()

    # Score calculado automaticamente (escala 0–10)
    # Ponderação: resultado 40%, win rate 20%, aproveitamento MEP 20%, gestão MEN 20%
    resultado_norm = min(max((resultado + 500) / 1000 * 10, 0), 10)
    wr_norm = win_rate / 10

    df_wins = df[wins_mask].copy()
    if not df_wins.empty:
        mep_vals = df_wins["mep"].replace(0, float('nan'))
        res_vals = df_wins["resultado_operacao"]
        aproveit = float((res_vals / mep_vals).mean() *
                         100) if mep_vals.notna().any() else 0
        aproveit = min(max(aproveit, 0), 100)
    else:
        aproveit = 0
    mep_norm = aproveit / 10

    df_loss = df[losses_mask].copy()
    if not df_loss.empty:
        men_vals = df_loss["men"].abs().replace(0, float('nan'))
        res_loss = df_loss["resultado_operacao"].abs()
        gestao = float((men_vals / res_loss).mean() *
                       100) if men_vals.notna().any() else 0
        gestao = min(max(gestao, 0), 100)
    else:
        gestao = 50  # sem losers = dia perfeito; neutro para não inflar o score
    men_norm = gestao / 10

    score_dia_calculado = round(
        resultado_norm * 0.4 +
        wr_norm * 0.2 +
        mep_norm * 0.2 +
        men_norm * 0.2,
        1
    )

    context = {
        "sem_dados": False, "sem_ops": False,
        "dias_disponiveis": dias_str, "data_sel": data_sel,
        "resultado_total":  round(resultado, 2),
        "win_rate":         round(win_rate, 1),
        "total_ops":        total_ops,
        "fator_lucro":      round(fator_lucro, 2) if fator_lucro else None,
        "drawdown_max":     round(drawdown_max, 2),
        "exposicao_neg":    round(exposicao_neg, 2),
        "maior_gain":       round(maior_gain, 2),
        "maior_gain_ativo": maior_gain_ativo,
        "maior_gain_hora":  maior_gain_hora,
        "maior_loss":       round(maior_loss, 2),
        "maior_loss_ativo": maior_loss_ativo,
        "maior_loss_hora":  maior_loss_hora,
        "tempo_medio_win":  tempo_medio_win,
        "tempo_medio_loss": tempo_medio_loss,
        "razao_tempo":      razao,
        "total_wins":       total_wins,
        "total_losses":     total_losses,
        "payoff_ratio_dia": metricas_av_dia["payoff_ratio"],
        "gain_medio_dia":   metricas_av_dia["gain_medio"],
        "loss_medio_dia":   metricas_av_dia["loss_medio"],
        "grafico_capital":  _grafico_capital_dia(df),
        "grafico_horario":  _grafico_horario_dia(df),
        "grafico_execucao": _grafico_execucao(df),
        "operacoes":        tabela,
        # Passo 6 — Anotação do Dia
        "anotacao_dia":        anotacao_dia,
        "score_dia_calculado": score_dia_calculado,
        "emocao_choices":      AnotacaoDia.EMOCAO_CHOICES,
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


def analise_setup(request):
    """
    Análise de performance agrupada por setup e por tag do Journal.
    Suporta filtro de período (data_inicio / data_fim).
    Depende do Passo 1 (JournalOperacao).
    """
    from django.db.models import Avg, Count, Sum

    data_inicio = request.GET.get("data_inicio", "").strip()
    data_fim = request.GET.get("data_fim",    "").strip()
    setup_sel = request.GET.get("setup",       "").strip()

    # ── Base: operações que têm journal ─────────────────────────────
    qs = JournalOperacao.objects.select_related("operacao").all()

    if data_inicio:
        qs = qs.filter(operacao__abertura__date__gte=data_inicio)
    if data_fim:
        qs = qs.filter(operacao__abertura__date__lte=data_fim)

    total_com_journal = qs.count()

    if total_com_journal == 0:
        return render(request, "trades/analise_setup.html", {
            "sem_dados":    True,
            "data_inicio":  data_inicio,
            "data_fim":     data_fim,
        })

    # ── Métricas por Setup ───────────────────────────────────────────
    # Coleta todos os registros uma vez para calcular EM e payoff
    todos_journals = list(qs.select_related("operacao"))

    def _metricas_grupo(journals_grupo):
        """Calcula métricas completas de uma lista de JournalOperacao."""
        resultados = [float(j.operacao.resultado_operacao)
                      for j in journals_grupo]
        total = len(resultados)
        if total == 0:
            return None

        wins = [r for r in resultados if r > 0]
        losses = [r for r in resultados if r <= 0]
        n_wins = len(wins)
        n_losses = len(losses)

        win_rate = (n_wins / total * 100) if total else 0.0
        resultado_total = sum(resultados)
        media_resultado = resultado_total / total

        gain_medio = (sum(wins) / n_wins) if n_wins else None
        loss_medio = (sum(losses) / n_losses) if n_losses else None

        if gain_medio is not None and loss_medio is not None:
            payoff = round(gain_medio / abs(loss_medio), 2)
            em = round((win_rate / 100 * gain_medio) +
                       ((1 - win_rate / 100) * loss_medio), 2)
        else:
            payoff = None
            em = None

        q_entradas = [j.qualidade_entrada for j in journals_grupo
                      if j.qualidade_entrada is not None]
        q_saidas = [j.qualidade_saida for j in journals_grupo
                    if j.qualidade_saida is not None]

        return {
            "total":            total,
            "n_wins":           n_wins,
            "n_losses":         n_losses,
            "win_rate":         round(win_rate, 1),
            "resultado_total":  round(resultado_total, 2),
            "media_resultado":  round(media_resultado, 2),
            "gain_medio":       round(gain_medio, 2) if gain_medio is not None else None,
            "loss_medio":       round(loss_medio, 2) if loss_medio is not None else None,
            "payoff":           payoff,
            "em":               em,
            "q_entrada_media":  round(sum(q_entradas) / len(q_entradas), 1) if q_entradas else None,
            "q_saida_media":    round(sum(q_saidas) / len(q_saidas),   1) if q_saidas else None,
        }

    # Agrupamento por setup
    from collections import defaultdict
    grupos_setup = defaultdict(list)
    grupos_tag = defaultdict(list)

    for j in todos_journals:
        chave = j.setup.strip() if j.setup and j.setup.strip() else "(sem setup)"
        grupos_setup[chave].append(j)

        # Cada tag é tratada separadamente
        for tag in j.tags_lista():
            grupos_tag[tag].append(j)

    metricas_setup = []
    for nome, journals_grupo in sorted(grupos_setup.items(),
                                       key=lambda x: x[0] == "(sem setup)"):
        m = _metricas_grupo(journals_grupo)
        if m:
            m["nome"] = nome
            m["sem_setup"] = (nome == "(sem setup)")
            metricas_setup.append(m)

    # Ordena por resultado total decrescente (sem setup vai pro fim)
    metricas_setup.sort(key=lambda x: (x["sem_setup"], -x["resultado_total"]))

    # Agrupamento por tag
    metricas_tag = []
    for nome, journals_grupo in grupos_tag.items():
        m = _metricas_grupo(journals_grupo)
        if m:
            m["nome"] = nome
            metricas_tag.append(m)
    metricas_tag.sort(key=lambda x: -x["resultado_total"])

    # ── Detalhe do setup selecionado ────────────────────────────────
    detalhe_setup = None
    detalhe_ops = []

    if setup_sel:
        journals_sel = [j for j in todos_journals
                        if (j.setup or "").strip() == setup_sel
                        or (not j.setup and setup_sel == "(sem setup)")]
        detalhe_setup = _metricas_grupo(journals_sel)
        if detalhe_setup:
            detalhe_setup["nome"] = setup_sel

        # Operações individuais do setup selecionado (mais recentes primeiro)
        for j in sorted(journals_sel,
                        key=lambda x: x.operacao.abertura, reverse=True):
            abertura_local = j.operacao.abertura.astimezone(TZ_BR)
            detalhe_ops.append({
                "abertura":         abertura_local,
                "ativo":            j.operacao.ativo,
                "resultado":        float(j.operacao.resultado_operacao),
                "is_win":           j.operacao.is_win,
                "tags_lista":       j.tags_lista(),
                "emocao":           j.get_emocao_display(),
                "emocao_slug":      j.emocao,
                "qualidade_entrada": j.qualidade_entrada,
                "qualidade_saida":   j.qualidade_saida,
                "anotacao":         j.anotacao,
            })

    # ── Setups disponíveis para filtro ──────────────────────────────
    setups_disponiveis = sorted(
        {(j.setup.strip() if j.setup and j.setup.strip() else "(sem setup)")
         for j in todos_journals}
    )

    # ── Gráficos ────────────────────────────────────────────────────
    grafico_setup = _grafico_analise_setup(metricas_setup)
    grafico_tag = _grafico_analise_tag(metricas_tag)

    context = {
        "sem_dados":           False,
        "data_inicio":         data_inicio,
        "data_fim":            data_fim,
        "setup_sel":           setup_sel,
        "total_com_journal":   total_com_journal,
        "metricas_setup":      metricas_setup,
        "metricas_tag":        metricas_tag,
        "detalhe_setup":       detalhe_setup,
        "detalhe_ops":         detalhe_ops,
        "setups_disponiveis":  setups_disponiveis,
        "grafico_setup":       grafico_setup,
        "grafico_tag":         grafico_tag,
    }
    return render(request, "trades/analise_setup.html", context)


def comparativo(request):
    """
    Comparativo lado a lado de dois períodos definidos pelo usuário.
    Mostra delta de cada métrica e gráficos sobrepostos de curva de capital.
    """
    # ── Parâmetros dos dois períodos ────────────────────────────────
    p1_inicio = request.GET.get("p1_inicio", "").strip()
    p1_fim = request.GET.get("p1_fim",    "").strip()
    p2_inicio = request.GET.get("p2_inicio", "").strip()
    p2_fim = request.GET.get("p2_fim",    "").strip()

    periodos_definidos = all([p1_inicio, p1_fim, p2_inicio, p2_fim])

    # ── Datas disponíveis para os seletores ─────────────────────────
    datas_disponiveis = list(
        Operacao.objects.dates("abertura", "day", order="ASC")
    )
    data_min = datas_disponiveis[0].strftime(
        "%Y-%m-%d") if datas_disponiveis else ""
    data_max = datas_disponiveis[-1].strftime(
        "%Y-%m-%d") if datas_disponiveis else ""

    if not periodos_definidos:
        return render(request, "trades/comparativo.html", {
            "sem_dados": not datas_disponiveis,
            "periodos_definidos": False,
            "data_min":          data_min,
            "data_max":          data_max,
            "p1_inicio": p1_inicio, "p1_fim": p1_fim,
            "p2_inicio": p2_inicio, "p2_fim": p2_fim,
        })

    # ── Carrega os dois conjuntos de operações ───────────────────────
    campos = [
        "abertura", "resultado_operacao", "resultado_operacao_pontos",
        "mep", "men",
    ]

    def _qs_periodo(ini, fim):
        qs = Operacao.objects.filter(
            abertura__date__gte=ini,
            abertura__date__lte=fim,
        ).values(*campos).order_by("abertura")
        if not qs.exists():
            return pd.DataFrame()
        df = pd.DataFrame(list(qs))
        df["abertura"] = pd.to_datetime(
            df["abertura"], utc=True).dt.tz_convert(TZ_BR)
        for col in ["resultado_operacao", "resultado_operacao_pontos", "mep", "men"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        return df

    df1 = _qs_periodo(p1_inicio, p1_fim)
    df2 = _qs_periodo(p2_inicio, p2_fim)

    # ── Calcula métricas de um DataFrame de período ─────────────────
    def _metricas_periodo(df):
        if df.empty:
            return None
        total = len(df)
        wins_mask = df["resultado_operacao"] > 0
        losses_mask = df["resultado_operacao"] <= 0
        n_wins = int(wins_mask.sum())
        n_losses = int(losses_mask.sum())
        win_rate = (n_wins / total * 100) if total else 0.0
        resultado = float(df["resultado_operacao"].sum())
        pontos = float(df["resultado_operacao_pontos"].sum())
        gain_medio = float(
            df.loc[wins_mask,   "resultado_operacao"].mean()) if n_wins else None
        loss_medio = float(
            df.loc[losses_mask, "resultado_operacao"].mean()) if n_losses else None
        payoff = round(gain_medio / abs(loss_medio),
                       2) if gain_medio and loss_medio else None
        em = round(
            (win_rate / 100 * gain_medio) +
            ((1 - win_rate / 100) * loss_medio), 2
        ) if gain_medio is not None and loss_medio is not None else None

        # Drawdown
        acum = df["resultado_operacao"].cumsum()
        pico = acum.cummax()
        drawdown = float((pico - acum).max())

        # MEP aproveitamento (winners)
        df_w = df[wins_mask & (df["mep"] > 0)]
        aprov_medio = round(
            float((df_w["resultado_operacao"] / df_w["mep"] * 100).mean()), 1
        ) if not df_w.empty else None

        dias = df["abertura"].dt.date.nunique()

        return {
            "total_ops":   total,
            "n_wins":      n_wins,
            "n_losses":    n_losses,
            "win_rate":    round(win_rate, 1),
            "resultado":   round(resultado, 2),
            "pontos":      round(pontos, 0),
            "gain_medio":  round(gain_medio, 2) if gain_medio else None,
            "loss_medio":  round(loss_medio, 2) if loss_medio else None,
            "payoff":      payoff,
            "em":          em,
            "drawdown":    round(drawdown, 2),
            "aprov_medio": aprov_medio,
            "dias":        dias,
        }

    m1 = _metricas_periodo(df1)
    m2 = _metricas_periodo(df2)

    # ── Deltas (P1 − P2) ────────────────────────────────────────────
    def _delta(v1, v2):
        """Retorna delta e classe CSS. None se qualquer valor ausente."""
        if v1 is None or v2 is None:
            return None, ""
        d = round(v1 - v2, 2)
        cls = "val-pos" if d > 0 else ("val-neg" if d < 0 else "")
        return d, cls

    deltas = {}
    if m1 and m2:
        for campo in ["resultado", "win_rate", "total_ops", "payoff",
                      "em", "drawdown", "aprov_medio", "pontos", "dias"]:
            deltas[campo] = _delta(m1.get(campo), m2.get(campo))
        # drawdown: delta negativo é MELHOR (menor drawdown)
        if deltas["drawdown"][0] is not None:
            d, _ = deltas["drawdown"]
            deltas["drawdown"] = (d, "val-pos" if d <
                                  0 else ("val-neg" if d > 0 else ""))

    # ── Gráfico: curvas de capital sobrepostas ───────────────────────
    grafico_curvas = _grafico_comparativo_curvas(
        df1, df2, p1_inicio, p1_fim, p2_inicio, p2_fim)

    # ── Gráfico: barras de métricas lado a lado ──────────────────────
    grafico_barras = _grafico_comparativo_barras(m1, m2)

    return render(request, "trades/comparativo.html", {
        "sem_dados": not datas_disponiveis,
        "periodos_definidos": True,
        "data_min":           data_min,
        "data_max":           data_max,
        "p1_inicio": p1_inicio, "p1_fim": p1_fim,
        "p2_inicio": p2_inicio, "p2_fim": p2_fim,
        "m1": m1, "m2": m2,
        "deltas":             deltas,
        "grafico_curvas":     grafico_curvas,
        "grafico_barras":     grafico_barras,
    })


def relatorio_mensal(request):
    """Visão consolidada por mês com comparativo mês a mês."""
    import calendar

    tz = pytz.timezone('America/Sao_Paulo')
    params = ParametrosTrader.carregar()

    # --- Filtro de mês selecionado ---
    mes_sel = request.GET.get('mes')  # formato: "2025-11"

    campos = [
        'abertura', 'fechamento', 'resultado_operacao',
        'resultado_operacao_pontos', 'mep', 'men',
        'total_acumulado', 'ativo',
    ]
    qs = Operacao.objects.all().values(*campos)

    if not qs.exists():
        return render(request, 'trades/relatorio_mensal.html', {
            'sem_dados': True,
            'meses_disponiveis': [],
            'mes_sel': None,
            'mes_dados': None,
            'todos_meses': [],
        })

    df = pd.DataFrame(list(qs))
    df['abertura'] = pd.to_datetime(df['abertura'], utc=True).dt.tz_convert(tz)
    df['fechamento'] = pd.to_datetime(
        df['fechamento'], utc=True).dt.tz_convert(tz)

    for col in ['resultado_operacao', 'resultado_operacao_pontos', 'mep', 'men']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    df['ano_mes'] = df['abertura'].dt.to_period('M')
    df['data'] = df['abertura'].dt.date

    # Lista de meses disponíveis (mais recente primeiro)
    periodos = sorted(df['ano_mes'].unique(), reverse=True)
    meses_disponiveis = [
        {
            'valor': str(p),
            'label': p.to_timestamp().strftime('%B/%Y').capitalize(),
        }
        for p in periodos
    ]

    # Mês selecionado padrão: mais recente
    if not mes_sel or mes_sel not in [m['valor'] for m in meses_disponiveis]:
        mes_sel = meses_disponiveis[0]['valor'] if meses_disponiveis else None

    # --- Cálculo por mês ---
    def _metricas_mes(df_m):
        total_ops = len(df_m)
        if total_ops == 0:
            return None
        wins = (df_m['resultado_operacao'] > 0).sum()
        losses = (df_m['resultado_operacao'] < 0).sum()
        win_rate = (wins / total_ops * 100) if total_ops else 0
        resultado = float(df_m['resultado_operacao'].sum())
        pontos = float(df_m['resultado_operacao_pontos'].sum())

        win_vals = df_m.loc[df_m['resultado_operacao']
                            > 0, 'resultado_operacao']
        loss_vals = df_m.loc[df_m['resultado_operacao']
                             < 0, 'resultado_operacao']
        avg_win = float(win_vals.mean()) if len(win_vals) else 0
        avg_loss = float(loss_vals.mean()) if len(loss_vals) else 0
        payoff = abs(avg_win / avg_loss) if avg_loss != 0 else 0
        em = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss)

        # Drawdown do mês
        df_ord = df_m.sort_values('abertura').copy()
        df_ord['acum'] = df_ord['resultado_operacao'].cumsum()
        df_ord['pico'] = df_ord['acum'].cummax()
        drawdown = float((df_ord['pico'] - df_ord['acum']).max())

        dias_operados = df_m['data'].nunique()
        dias_positivos = df_m.groupby('data')['resultado_operacao'].sum()
        melhor_dia_val = float(dias_positivos.max())
        pior_dia_val = float(dias_positivos.min())
        melhor_dia_dt = dias_positivos.idxmax()
        pior_dia_dt = dias_positivos.idxmin()

        return {
            'total_ops': total_ops,
            'wins': int(wins),
            'losses': int(losses),
            'win_rate': round(win_rate, 1),
            'resultado': resultado,
            'pontos': round(pontos, 0),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'payoff': round(payoff, 2),
            'em': round(em, 2),
            'drawdown': round(drawdown, 2),
            'dias_operados': dias_operados,
            'melhor_dia_val': round(melhor_dia_val, 2),
            'pior_dia_val': round(pior_dia_val, 2),
            'melhor_dia_dt': melhor_dia_dt,
            'pior_dia_dt': pior_dia_dt,
        }

    # Todos os meses para a tabela comparativa
    todos_meses_raw = []
    for p in periodos:
        df_m = df[df['ano_mes'] == p].copy()
        m = _metricas_mes(df_m)
        if m:
            m['periodo'] = str(p)
            m['label'] = p.to_timestamp().strftime('%b/%Y').capitalize()
            todos_meses_raw.append(m)

    # Delta entre meses consecutivos
    todos_meses = []
    for i, m in enumerate(todos_meses_raw):
        m_copy = dict(m)
        if i < len(todos_meses_raw) - 1:
            ant = todos_meses_raw[i + 1]
            m_copy['delta_resultado'] = round(
                m['resultado'] - ant['resultado'], 2)
            m_copy['delta_win_rate'] = round(
                m['win_rate'] - ant['win_rate'], 1)
            m_copy['delta_ops'] = m['total_ops'] - ant['total_ops']
            m_copy['delta_em'] = round(m['em'] - ant['em'], 2)
        else:
            m_copy['delta_resultado'] = None
            m_copy['delta_win_rate'] = None
            m_copy['delta_ops'] = None
            m_copy['delta_em'] = None
        todos_meses.append(m_copy)

    # Métricas do mês selecionado
    periodo_sel = pd.Period(mes_sel, freq='M')
    df_sel = df[df['ano_mes'] == periodo_sel].copy()
    mes_dados = _metricas_mes(df_sel)

    if mes_dados:
        mes_dados['periodo'] = mes_sel
        mes_dados['label'] = periodo_sel.to_timestamp().strftime(
            '%B/%Y').capitalize()

        # Retorno % sobre capital
        capital = float(
            params.capital_inicial) if params.capital_inicial else 0
        if capital > 0:
            mes_dados['retorno_pct'] = round(
                mes_dados['resultado'] / capital * 100, 2)
        else:
            mes_dados['retorno_pct'] = None

        # --- Gráfico de barras: resultado por mês ---
        labels_meses = [m['label'] for m in reversed(todos_meses)]
        vals_resultado = [m['resultado'] for m in reversed(todos_meses)]
        cores_barras = ['#3fb68b' if v >=
                        0 else '#e05c5c' for v in vals_resultado]

        fig_barras = go.Figure()
        fig_barras.add_trace(go.Bar(
            x=labels_meses,
            y=vals_resultado,
            marker_color=cores_barras,
            text=[f"R$ {v:,.0f}" for v in vals_resultado],
            textposition='outside',
            hovertemplate='%{x}<br>R$ %{y:,.2f}<extra></extra>',
        ))
        fig_barras.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#b8c4ce', family='monospace'),
            margin=dict(l=10, r=10, t=10, b=40),
            height=280,
            xaxis=dict(showgrid=False, tickfont=dict(size=11)),
            yaxis=dict(
                showgrid=True,
                gridcolor='#21262d',
                tickprefix='R$ ',
                tickformat=',.0f',
                zeroline=True,
                zerolinecolor='#444c56',
            ),
            showlegend=False,
        )
        grafico_barras = fig_barras.to_html(
            full_html=False, include_plotlyjs=False)

        # --- Gráfico de evolução do Win Rate por mês ---
        wr_vals = [m['win_rate'] for m in reversed(todos_meses)]
        fig_wr = go.Figure()
        fig_wr.add_trace(go.Scatter(
            x=labels_meses,
            y=wr_vals,
            mode='lines+markers',
            line=dict(color='#4da6ff', width=2),
            marker=dict(size=7, color='#4da6ff'),
            fill='tozeroy',
            fillcolor='rgba(77,166,255,0.1)',
            hovertemplate='%{x}<br>Win Rate: %{y:.1f}%<extra></extra>',
        ))
        fig_wr.add_hline(
            y=50,
            line_dash='dash',
            line_color='#e6a817',
            annotation_text='50%',
            annotation_font_color='#e6a817',
        )
        fig_wr.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#b8c4ce', family='monospace'),
            margin=dict(l=10, r=10, t=10, b=40),
            height=240,
            xaxis=dict(showgrid=False, tickfont=dict(size=11)),
            yaxis=dict(
                showgrid=True,
                gridcolor='#21262d',
                ticksuffix='%',
                range=[0, 100],
            ),
            showlegend=False,
        )
        grafico_win_rate = fig_wr.to_html(
            full_html=False, include_plotlyjs=False)

        mes_dados['grafico_barras'] = grafico_barras
        mes_dados['grafico_win_rate'] = grafico_win_rate

    return render(request, 'trades/relatorio_mensal.html', {
        'sem_dados': False,
        'meses_disponiveis': meses_disponiveis,
        'mes_sel': mes_sel,
        'mes_dados': mes_dados,
        'todos_meses': todos_meses,
        'capital_inicial': float(params.capital_inicial) if params.capital_inicial else 0,
    })
