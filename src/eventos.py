"""Detecção de eventos climáticos adversos para o café: geada e seca.

Nota de calibração (geada de jul/2021): nas células de ~50 km do MERRA-2
(NASA POWER), o T2M_MIN de abrigo ficou entre 0,9 °C (Avaré) e 5,9 °C
(Franca) nas duas ondas (19–20/07 e 29–30/07) — e mesmo assim o café queimou
na Alta Mogiana. A temperatura de relvado corre tipicamente 4–6 °C abaixo do
abrigo, e a célula de 50 km suaviza os vales frios. Por isso o limiar padrão
de *risco* é 6 °C no T2M_MIN, com severidade por faixas.
"""
from __future__ import annotations

import pandas as pd

from .dados import power

LIMIAR_RISCO_C = 6.0

# (limite superior do T2M_MIN, rótulo) — avaliado em ordem
FAIXAS_SEVERIDADE = [
    (0.0, "extrema"),
    (2.0, "severa"),
    (4.0, "moderada"),
    (LIMIAR_RISCO_C, "atenção"),
]


def severidade_geada(t_min_c: float) -> str | None:
    """Classifica o T2M_MIN (célula ~50 km) em faixa de severidade de geada."""
    for limite, rotulo in FAIXAS_SEVERIDADE:
        if t_min_c <= limite:
            return rotulo
    return None


def detectar_geadas(
    lat: float,
    lon: float,
    inicio,
    fim,
    limiar_c: float = LIMIAR_RISCO_C,
) -> pd.DataFrame:
    """Eventos de risco de geada em um ponto (dias consecutivos agrupados).

    Retorna DataFrame: data_inicio, data_fim, dias, t2m_min, severidade.
    """
    clima = power.clima_diario(lat, lon, inicio, fim, parametros=("T2M_MIN",))
    frios = clima[clima["T2M_MIN"] <= limiar_c]
    if frios.empty:
        return pd.DataFrame(
            columns=["data_inicio", "data_fim", "dias", "t2m_min", "severidade"]
        )
    datas = frios.index.to_series()
    grupo = (datas.diff().dt.days > 1).cumsum()
    eventos = []
    for _, bloco in frios.groupby(grupo):
        t_min = float(bloco["T2M_MIN"].min())
        eventos.append(
            {
                "data_inicio": bloco.index.min().date(),
                "data_fim": bloco.index.max().date(),
                "dias": len(bloco),
                "t2m_min": round(t_min, 1),
                "severidade": severidade_geada(t_min),
            }
        )
    return pd.DataFrame(eventos)


def geadas_por_edr(edrs, inicio, fim, limiar_c: float = LIMIAR_RISCO_C) -> pd.DataFrame:
    """Eventos de geada nos centroides dos EDRs (GeoDataFrame de geo.carregar_edrs)."""
    quadros = []
    for _, edr in edrs.iterrows():
        centro = edr.geometry.centroid
        eventos = detectar_geadas(centro.y, centro.x, inicio, fim, limiar_c)
        if eventos.empty:
            continue
        eventos.insert(0, "edr", edr["edr"])
        eventos.insert(1, "edr_chave", edr["edr_chave"])
        quadros.append(eventos)
    if not quadros:
        return pd.DataFrame(
            columns=["edr", "edr_chave", "data_inicio", "data_fim", "dias", "t2m_min", "severidade"]
        )
    return pd.concat(quadros, ignore_index=True).sort_values(
        ["data_inicio", "t2m_min"]
    ).reset_index(drop=True)


def deficit_hidrico_florada(
    lat: float,
    lon: float,
    ano: int,
    referencia: tuple[int, int] = (1995, 2024),
) -> dict:
    """Chuva acumulada na florada (set–nov) do ano vs a climatologia local.

    Retorna dict com chuva_mm, media_mm, desvio_mm, anomalia_pct e z_score.
    Valores negativos de anomalia = seca na janela crítica do café.
    """
    inicio_ref = f"{referencia[0]}-09-01"
    fim = f"{ano}-11-30"
    clima = power.clima_diario(lat, lon, inicio_ref, fim, parametros=("PRECTOTCORR",))
    florada = clima[clima.index.month.isin([9, 10, 11])]
    por_ano = florada.groupby(florada.index.year)["PRECTOTCORR"].sum()
    historico = por_ano[(por_ano.index >= referencia[0]) & (por_ano.index <= referencia[1])]
    chuva = float(por_ano.get(ano, float("nan")))
    media = float(historico.mean())
    desvio = float(historico.std())
    return {
        "ano": ano,
        "chuva_mm": round(chuva, 1),
        "media_mm": round(media, 1),
        "desvio_mm": round(desvio, 1),
        "anomalia_pct": round(100 * (chuva - media) / media, 1),
        "z_score": round((chuva - media) / desvio, 2),
    }
