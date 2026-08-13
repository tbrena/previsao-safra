"""Sistema 2 — nowcast de rendimento de café por EDR.

Dataset EDR × ano-safra (2012–2025) com features conhecidas até o meio do
ano da colheita, treinado contra o rendimento do IEA:

- clima por janela fenológica (NASA POWER no centroide do EDR, cache local):
  florada (set–nov do ano anterior), enchimento (dez–mar), inverno anterior
  (geada que danifica a estrutura), chuva do ciclo completo
- bienalidade: rendimento dos dois anos anteriores e o delta entre eles
- área em produção (nível e variação) — o levantamento do próprio ano sai
  antes da colheita, então é informação legítima de nowcast
- incentivo de preço: média 12 m / média 36 m do preço recebido (café
  secagem natural) até março do ano-safra

Validação leave-one-year-out (o modelo nunca vê o ano que prevê), comparada
com dois baselines: persistência (rendimento do ano anterior) e média bienal
do EDR (média dos anos de mesma fase).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .dados import geo, iea, power

AREA_MINIMA_HA = 2000.0  # EDRs com café relevante (média 2010–2025)
ANO_INICIAL_TREINO = 2012  # precisa de 2 lags a partir de 2010
JANELAS_CLIMA_INICIO = "2009-01-01"

COLUNAS_FEATURES = [
    "chuva_florada_mm",
    "anom_florada_pct",
    "dias_tmax33_florada",
    "chuva_enchimento_mm",
    "anom_enchimento_pct",
    "tmin_inverno_anterior",
    "dias_frio_inverno_anterior",
    "chuva_ciclo_mm",
    "rendimento_a1",
    "rendimento_a2",
    "delta_bienal",
    "log_area",
    "var_area_pct",
    "razao_preco",
]


def clima_edr(edr_chave: str, centroide, fim: str) -> pd.DataFrame:
    """Série diária de clima do centroide do EDR, com cache em CSV."""
    pasta = config.PASTA_PROCESSADOS / "clima"
    pasta.mkdir(parents=True, exist_ok=True)
    cache = pasta / f"{edr_chave.replace(' ', '_')}.csv"
    if cache.exists():
        serie = pd.read_csv(cache, index_col=0, parse_dates=True)
        if serie.index.max() >= pd.Timestamp(fim) - pd.Timedelta(days=5):
            return serie
    serie = power.clima_diario(
        centroide.y,
        centroide.x,
        JANELAS_CLIMA_INICIO,
        fim,
        parametros=("T2M", "T2M_MAX", "T2M_MIN", "PRECTOTCORR"),
    )
    serie.to_csv(cache)
    return serie


def _janela(clima: pd.DataFrame, inicio: str, fim: str) -> pd.DataFrame:
    return clima.loc[inicio:fim]


def features_clima(clima: pd.DataFrame, ano: int, climatologia: dict) -> dict:
    """Features climáticas do ano-safra ``ano`` (colheita mai–set)."""
    florada = _janela(clima, f"{ano - 1}-09-01", f"{ano - 1}-11-30")
    enchimento = _janela(clima, f"{ano - 1}-12-01", f"{ano}-03-31")
    inverno_ant = _janela(clima, f"{ano - 1}-05-01", f"{ano - 1}-08-31")
    ciclo = _janela(clima, f"{ano - 1}-09-01", f"{ano}-04-30")

    chuva_florada = float(florada["PRECTOTCORR"].sum())
    chuva_enchimento = float(enchimento["PRECTOTCORR"].sum())
    return {
        "chuva_florada_mm": round(chuva_florada, 1),
        "anom_florada_pct": round(
            100 * (chuva_florada - climatologia["florada"]) / climatologia["florada"], 1
        ),
        "dias_tmax33_florada": int((florada["T2M_MAX"] >= 33.0).sum()),
        "chuva_enchimento_mm": round(chuva_enchimento, 1),
        "anom_enchimento_pct": round(
            100 * (chuva_enchimento - climatologia["enchimento"]) / climatologia["enchimento"], 1
        ),
        "tmin_inverno_anterior": round(float(inverno_ant["T2M_MIN"].min()), 1),
        "dias_frio_inverno_anterior": int((inverno_ant["T2M_MIN"] <= 2.0).sum()),
        "chuva_ciclo_mm": round(float(ciclo["PRECTOTCORR"].sum()), 1),
    }


def _climatologia(clima: pd.DataFrame, anos=range(2010, 2025)) -> dict:
    floradas, enchimentos = [], []
    for ano in anos:
        floradas.append(_janela(clima, f"{ano - 1}-09-01", f"{ano - 1}-11-30")["PRECTOTCORR"].sum())
        enchimentos.append(_janela(clima, f"{ano - 1}-12-01", f"{ano}-03-31")["PRECTOTCORR"].sum())
    return {"florada": float(np.mean(floradas)), "enchimento": float(np.mean(enchimentos))}


def montar_dataset(fim_clima: str, ano_previsao: int | None = None) -> pd.DataFrame:
    """Dataset completo (features + alvo). Inclui o ano de previsão sem alvo."""
    cafe = iea.cafe_edr(config.PASTA_IEA)
    medias = cafe.groupby("edr_chave")["area_producao_ha"].mean()
    elegiveis = sorted(medias[medias >= AREA_MINIMA_HA].index)

    edrs = geo.carregar_edrs(config.CAMINHO_EDRS)
    edrs = edrs[edrs["edr_chave"].isin(elegiveis)]

    precos = iea.preco_recebido(config.PASTA_IEA_RECEBIDOS)
    serie_preco = (
        precos[(precos["produto"] == "Café benef. secagem natural") & (precos["moeda"] == "R$")]
        .set_index("data")["preco"]
        .sort_index()
    )

    ultimo_ano_iea = int(cafe["ano"].max())
    anos_alvo = list(range(ANO_INICIAL_TREINO, ultimo_ano_iea + 1))
    if ano_previsao and ano_previsao not in anos_alvo:
        anos_alvo.append(ano_previsao)

    linhas = []
    for _, edr in edrs.iterrows():
        chave = edr["edr_chave"]
        clima = clima_edr(chave, edr.geometry.centroid, fim_clima)
        climatologia = _climatologia(clima)
        historico = cafe[cafe["edr_chave"] == chave].set_index("ano")

        for ano in anos_alvo:
            r1 = historico["rendimento_kg_ha"].get(ano - 1)
            r2 = historico["rendimento_kg_ha"].get(ano - 2)
            # área do ano; para o ano de previsão (sem levantamento) usa a última
            area = historico["area_producao_ha"].get(ano)
            if pd.isna(area) or area is None:
                area = historico["area_producao_ha"].get(ano - 1)
            area_a1 = historico["area_producao_ha"].get(ano - 1)
            if any(pd.isna(v) or v is None for v in (r1, r2, area, area_a1)):
                continue

            ate_marco = serie_preco.loc[: f"{ano}-03-31"]
            preco_12m = ate_marco.tail(12).mean()
            preco_36m = ate_marco.tail(36).mean()

            linha = {
                "edr_chave": chave,
                "edr": edr["edr"],
                "ano": ano,
                **features_clima(clima, ano, climatologia),
                "rendimento_a1": float(r1),
                "rendimento_a2": float(r2),
                "delta_bienal": float(r1 - r2),
                "log_area": float(np.log(area)),
                "var_area_pct": round(100 * (area - area_a1) / area_a1, 2),
                "razao_preco": round(float(preco_12m / preco_36m), 3),
                "area_ha": float(area),
                "rendimento_kg_ha": (
                    float(historico["rendimento_kg_ha"].get(ano))
                    if ano in historico.index
                    else np.nan
                ),
            }
            linhas.append(linha)
    return pd.DataFrame(linhas)


def validar_loyo(dataset: pd.DataFrame):
    """Validação leave-one-year-out + baselines. Retorna (previsões, métricas)."""
    from sklearn.ensemble import RandomForestRegressor

    treino = dataset.dropna(subset=["rendimento_kg_ha"]).copy()
    anos = sorted(treino["ano"].unique())
    previsoes = []
    for ano in anos:
        fora = treino[treino["ano"] == ano]
        dentro = treino[treino["ano"] != ano]
        modelo = RandomForestRegressor(
            n_estimators=500, min_samples_leaf=2, random_state=42, n_jobs=-1
        )
        modelo.fit(dentro[COLUNAS_FEATURES], dentro["rendimento_kg_ha"])
        parcial = fora[["edr_chave", "edr", "ano", "rendimento_kg_ha", "rendimento_a1", "rendimento_a2", "area_ha"]].copy()
        parcial["previsto"] = modelo.predict(fora[COLUNAS_FEATURES])
        previsoes.append(parcial)
    resultado = pd.concat(previsoes, ignore_index=True)

    erro = resultado["previsto"] - resultado["rendimento_kg_ha"]
    erro_persistencia = resultado["rendimento_a1"] - resultado["rendimento_kg_ha"]
    erro_bienal = resultado["rendimento_a2"] - resultado["rendimento_kg_ha"]
    metricas = {
        "mae_modelo": float(erro.abs().mean()),
        "mae_persistencia": float(erro_persistencia.abs().mean()),
        "mae_bienal": float(erro_bienal.abs().mean()),
        "rmse_modelo": float(np.sqrt((erro**2).mean())),
        "vies_modelo": float(erro.mean()),
        "n_observacoes": int(len(resultado)),
        "anos": f"{anos[0]}–{anos[-1]}",
    }
    return resultado, metricas


def treinar_final(dataset: pd.DataFrame):
    """Treina no histórico completo e devolve (modelo, importâncias)."""
    from sklearn.ensemble import RandomForestRegressor

    treino = dataset.dropna(subset=["rendimento_kg_ha"])
    modelo = RandomForestRegressor(
        n_estimators=800, min_samples_leaf=2, random_state=42, n_jobs=-1
    )
    modelo.fit(treino[COLUNAS_FEATURES], treino["rendimento_kg_ha"])
    importancias = (
        pd.Series(modelo.feature_importances_, index=COLUNAS_FEATURES)
        .sort_values(ascending=False)
        .rename("importancia")
        .reset_index()
        .rename(columns={"index": "feature"})
    )
    return modelo, importancias
