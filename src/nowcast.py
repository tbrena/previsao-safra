"""Sistema 2 — nowcast de rendimento por EDR, multi-cultura.

Cada cultura é descrita no registro ``CULTURAS``: produtos do IEA (com
desdobramentos históricos somáveis), unidade, alvo (kg/ha, ou cx/pé para a
laranja — que o IEA mede em pés desde 1983), janelas fenológicas próprias,
capacidade (área ou pés), preço de referência e fontes de NDVI.

O desenho do modelo é o validado no café: HistGradientBoosting (aceita
ausentes), lags do alvo + âncora (média das safras de mesma fase para
perenes; das últimas 3 para anuais), clima por janela, capacidade, incentivo
de preço e anomalia de NDVI quando existe máscara MapBiomas confiável.
Validação leave-one-year-out contra persistência e lag-2.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .dados import geo, iea, power

JANELAS_CLIMA_INICIO = "2000-01-01"

# janela = (mês inicial, mês final, offset do ano no início, offset no fim),
# relativos ao ano-safra A
CULTURAS: dict[str, dict] = {
    "cafe": {
        "rotulo": "Café",
        "produtos": ["Café (beneficiado)"],
        "kg_por_unidade": 60.0,
        "unidade_producao": "sc 60 kg",
        "preco_produto": "Café benef. secagem natural",
        "alvo": "rendimento_kg_ha",
        "unidade_alvo": "kg/ha",
        "capacidade": "area_producao_ha",
        "perene": True,
        "janelas": {
            "critica": (9, 11, -1, -1),      # florada
            "secundaria": (12, 3, -1, 0),    # enchimento do grão
            "fria": (5, 8, -1, -1),          # geada danifica a safra seguinte
            "ciclo": (9, 4, -1, 0),
        },
        # 2001 = primeiro ano medido em hectares (antes: pés, sem conversão limpa)
        "ano_inicial": 2001,
        "capacidade_minima": 2000.0,
        "celulas": "celulas_cafe_2023.csv",
        "ndvi": "ndvi_edr.csv",
    },
    "laranja": {
        "rotulo": "Laranja",
        "produtos": ["Laranja"],
        "kg_por_unidade": 40.8,
        "unidade_producao": "cx 40,8 kg",
        "preco_produto": "Laranja para indústria",
        "alvo": "rendimento_unid_por_pe",   # cx/pé — como a citricultura mede
        "unidade_alvo": "cx/pé",
        "capacidade": "pes_producao",
        "perene": True,
        "janelas": {
            "critica": (9, 11, -1, -1),      # florada (set–out após estresse)
            "secundaria": (12, 3, -1, 0),    # pegamento/crescimento do fruto
            "fria": (5, 8, -1, -1),
            "ciclo": (9, 4, -1, 0),
        },
        "ano_inicial": 1985,
        "capacidade_minima": 1_000_000.0,    # pés em produção
        "celulas": "celulas_citros_2023.csv",
        "ndvi": "ndvi_citros.csv",
    },
    "amendoim": {
        "rotulo": "Amendoim",
        "produtos": ["Amendoim", "Amendoim das águas", "Amendoim da seca"],
        "kg_por_unidade": 25.0,
        "unidade_producao": "sc 25 kg",
        "preco_produto": "Amendoim em casca",
        "alvo": "rendimento_kg_ha",
        "unidade_alvo": "kg/ha",
        "capacidade": "area_producao_ha",
        "perene": False,
        "janelas": {
            "critica": (10, 12, -1, -1),     # plantio/estabelecimento
            "secundaria": (1, 3, 0, 0),      # enchimento das vagens
            "fria": (5, 8, -1, -1),          # inócua (sem geada no ciclo)
            "ciclo": (10, 3, -1, 0),
        },
        "ano_inicial": 1985,
        "capacidade_minima": 1000.0,
        "celulas": None,                     # sem classe MapBiomas própria
        "ndvi": None,
    },
    "milho_safrinha": {
        "rotulo": "Milho safrinha",
        "produtos": ["Milho (safrinha)"],
        "kg_por_unidade": 60.0,
        "unidade_producao": "sc 60 kg",
        "preco_produto": "Milho",
        "alvo": "rendimento_kg_ha",
        "unidade_alvo": "kg/ha",
        "capacidade": "area_producao_ha",
        "perene": False,
        "janelas": {
            "critica": (2, 4, 0, 0),         # plantio/floração
            "secundaria": (4, 6, 0, 0),      # enchimento + veranico
            "fria": (5, 7, 0, 0),            # geada DENTRO do ciclo
            "ciclo": (1, 6, 0, 0),
        },
        "ano_inicial": 1992,                 # série IEA desde 1990 + lags
        "capacidade_minima": 1000.0,
        "celulas": None,                     # milho cai em "outras temporárias"
        "ndvi": None,
    },
}

COLUNAS_FEATURES = [
    "chuva_critica_mm",
    "anom_critica_pct",
    "dias_tmax33_critica",
    "chuva_secundaria_mm",
    "anom_secundaria_pct",
    "tmin_fria",
    "dias_frio_fria",
    "chuva_ciclo_mm",
    "rendimento_a1",
    "rendimento_a2",
    "ancora_bienal",
    "delta_bienal",
    "log_capacidade",
    "var_capacidade_pct",
    "razao_preco",
    "anom_ndvi_florada",
    "anom_ndvi_enchimento",
]


def clima_edr(edr_chave: str, centroide, fim: str) -> pd.DataFrame:
    """Série diária de clima do centroide do EDR, com cache em CSV."""
    pasta = config.PASTA_PROCESSADOS / "clima"
    pasta.mkdir(parents=True, exist_ok=True)
    cache = pasta / f"{edr_chave.replace(' ', '_')}.csv"
    if cache.exists():
        serie = pd.read_csv(cache, index_col=0, parse_dates=True)
        fim_ok = serie.index.max() >= pd.Timestamp(fim) - pd.Timedelta(days=5)
        inicio_ok = serie.index.min() <= pd.Timestamp(JANELAS_CLIMA_INICIO) + pd.Timedelta(days=5)
        if fim_ok and inicio_ok:
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


def _datas_janela(ano: int, spec: tuple[int, int, int, int]) -> tuple[str, str]:
    m0, m1, off0, off1 = spec
    inicio = f"{ano + off0}-{m0:02d}-01"
    fim = pd.Period(f"{ano + off1}-{m1:02d}", freq="M").end_time.date().isoformat()
    return inicio, fim


def _janela(clima: pd.DataFrame, ano: int, spec) -> pd.DataFrame:
    inicio, fim = _datas_janela(ano, spec)
    return clima.loc[inicio:fim]


def features_clima(clima: pd.DataFrame, ano: int, climatologia: dict, janelas: dict) -> dict:
    critica = _janela(clima, ano, janelas["critica"])
    secundaria = _janela(clima, ano, janelas["secundaria"])
    fria = _janela(clima, ano, janelas["fria"])
    ciclo = _janela(clima, ano, janelas["ciclo"])

    chuva_critica = float(critica["PRECTOTCORR"].sum())
    chuva_secundaria = float(secundaria["PRECTOTCORR"].sum())
    return {
        "chuva_critica_mm": round(chuva_critica, 1),
        "anom_critica_pct": round(
            100 * (chuva_critica - climatologia["critica"]) / climatologia["critica"], 1
        ),
        "dias_tmax33_critica": int((critica["T2M_MAX"] >= 33.0).sum()),
        "chuva_secundaria_mm": round(chuva_secundaria, 1),
        "anom_secundaria_pct": round(
            100 * (chuva_secundaria - climatologia["secundaria"]) / climatologia["secundaria"], 1
        ),
        "tmin_fria": round(float(fria["T2M_MIN"].min()), 1),
        "dias_frio_fria": int((fria["T2M_MIN"] <= 2.0).sum()),
        "chuva_ciclo_mm": round(float(ciclo["PRECTOTCORR"].sum()), 1),
    }


def _climatologia(clima: pd.DataFrame, janelas: dict, anos=range(2001, 2021)) -> dict:
    criticas, secundarias = [], []
    for ano in anos:
        criticas.append(_janela(clima, ano, janelas["critica"])["PRECTOTCORR"].sum())
        secundarias.append(_janela(clima, ano, janelas["secundaria"])["PRECTOTCORR"].sum())
    return {"critica": float(np.mean(criticas)), "secundaria": float(np.mean(secundarias))}


def montar_dataset(
    fim_clima: str,
    cultura: str = "cafe",
    ano_previsao: int | None = None,
) -> pd.DataFrame:
    """Dataset (features + alvo na coluna ``alvo``) da cultura escolhida."""
    cfg = CULTURAS[cultura]
    dados = iea.producao_edr(config.PASTA_IEA, cfg["produtos"], cfg["kg_por_unidade"])
    if cfg["alvo"] not in dados.columns:
        raise RuntimeError(f"alvo {cfg['alvo']!r} indisponível para {cultura}")

    capacidade_media = dados.groupby("edr_chave")[cfg["capacidade"]].mean()
    elegiveis = sorted(capacidade_media[capacidade_media >= cfg["capacidade_minima"]].index)
    edrs = geo.carregar_edrs(config.CAMINHO_EDRS)
    edrs = edrs[edrs["edr_chave"].isin(elegiveis)]

    precos = iea.preco_recebido(config.PASTA_IEA_RECEBIDOS)
    serie_preco = (
        precos[(precos["produto"] == cfg["preco_produto"]) & (precos["moeda"] == "R$")]
        .set_index("data")["preco"]
        .sort_index()
    )

    ultimo_ano = int(dados.dropna(subset=[cfg["alvo"]])["ano"].max())
    anos_alvo = list(range(cfg["ano_inicial"], ultimo_ano + 1))
    if ano_previsao and ano_previsao not in anos_alvo:
        anos_alvo.append(ano_previsao)

    pares_ancora = (2, 4, 6, 8) if cfg["perene"] else (1, 2, 3)

    linhas = []
    for _, edr in edrs.iterrows():
        chave = edr["edr_chave"]
        clima = clima_edr(chave, edr.geometry.centroid, fim_clima)
        climatologia = _climatologia(clima, cfg["janelas"])
        historico = dados[dados["edr_chave"] == chave].set_index("ano")

        def _valor(coluna, a):
            if coluna not in historico.columns:
                return np.nan
            v = historico[coluna].get(a)
            return float(v) if v is not None and not pd.isna(v) else np.nan

        for ano in anos_alvo:
            r1 = _valor(cfg["alvo"], ano - 1)
            r2 = _valor(cfg["alvo"], ano - 2)
            pares = [_valor(cfg["alvo"], ano - k) for k in pares_ancora]
            ancora = float(np.nanmean(pares)) if not all(np.isnan(v) for v in pares) else np.nan

            cap = _valor(cfg["capacidade"], ano)
            if np.isnan(cap):
                cap = _valor(cfg["capacidade"], ano - 1)
            cap_a1 = _valor(cfg["capacidade"], ano - 1)
            if np.isnan(cap) or cap <= 0:
                continue

            janela36 = serie_preco.loc[: f"{ano}-03-31"].tail(36)
            razao = (
                float(janela36.tail(12).mean() / janela36.mean())
                if len(janela36) >= 30
                else np.nan
            )

            linhas.append(
                {
                    "edr_chave": chave,
                    "edr": edr["edr"],
                    "ano": ano,
                    **features_clima(clima, ano, climatologia, cfg["janelas"]),
                    "rendimento_a1": r1,
                    "rendimento_a2": r2,
                    "ancora_bienal": ancora,
                    "delta_bienal": r1 - r2,
                    "log_capacidade": float(np.log(cap)),
                    "var_capacidade_pct": (
                        round(100 * (cap - cap_a1) / cap_a1, 2)
                        if not np.isnan(cap_a1) and cap_a1 > 0
                        else np.nan
                    ),
                    "razao_preco": round(razao, 3) if not np.isnan(razao) else np.nan,
                    "capacidade": float(cap),
                    "alvo": _valor(cfg["alvo"], ano),
                }
            )

    dataset = pd.DataFrame(linhas)
    caminho_ndvi = config.PASTA_PROCESSADOS / cfg["ndvi"] if cfg["ndvi"] else None
    if caminho_ndvi is not None and caminho_ndvi.exists():
        from .dados import ndvi_edr as _ndvi

        serie_ndvi = pd.read_csv(caminho_ndvi)
        dataset = dataset.merge(
            _ndvi.anomalias(serie_ndvi), on=["edr_chave", "ano"], how="left"
        )
    for coluna in ("anom_ndvi_florada", "anom_ndvi_enchimento"):
        if coluna not in dataset.columns:
            dataset[coluna] = np.nan
    return dataset


def _novo_modelo():
    from sklearn.ensemble import HistGradientBoostingRegressor

    return HistGradientBoostingRegressor(
        max_iter=600,
        learning_rate=0.05,
        min_samples_leaf=5,
        l2_regularization=1.0,
        random_state=42,
    )


def _colunas_uteis(dados: pd.DataFrame, colunas: list[str]) -> list[str]:
    """Descarta colunas sem variação (evita bug de binning do sklearn)."""
    return [c for c in colunas if c in dados.columns and dados[c].nunique(dropna=True) >= 2]


def validar_loyo(dataset: pd.DataFrame, colunas: list[str] | None = None):
    """Validação leave-one-year-out + baselines. Retorna (previsões, métricas)."""
    colunas = colunas or COLUNAS_FEATURES
    treino = dataset.dropna(subset=["alvo"]).copy()
    anos = sorted(treino["ano"].unique())
    previsoes = []
    for ano in anos:
        fora = treino[treino["ano"] == ano]
        dentro = treino[treino["ano"] != ano]
        uteis = _colunas_uteis(dentro, colunas)
        modelo = _novo_modelo()
        modelo.fit(dentro[uteis], dentro["alvo"])
        parcial = fora[["edr_chave", "edr", "ano", "alvo", "rendimento_a1", "rendimento_a2", "capacidade"]].copy()
        parcial["previsto"] = modelo.predict(fora[uteis])
        previsoes.append(parcial)
    resultado = pd.concat(previsoes, ignore_index=True)

    erro = resultado["previsto"] - resultado["alvo"]
    persistencia = resultado.dropna(subset=["rendimento_a1"])
    lag2 = resultado.dropna(subset=["rendimento_a2"])
    metricas = {
        "mae_modelo": float(erro.abs().mean()),
        "mae_persistencia": float(
            (persistencia["rendimento_a1"] - persistencia["alvo"]).abs().mean()
        ),
        "mae_bienal": float((lag2["rendimento_a2"] - lag2["alvo"]).abs().mean()),
        "rmse_modelo": float(np.sqrt((erro**2).mean())),
        "vies_modelo": float(erro.mean()),
        "n_observacoes": int(len(resultado)),
        "anos": f"{anos[0]}–{anos[-1]}",
    }
    return resultado, metricas


def treinar_final(dataset: pd.DataFrame):
    """Treina no histórico completo; devolve (modelo, colunas, importâncias)."""
    from sklearn.inspection import permutation_importance

    treino = dataset.dropna(subset=["alvo"])
    uteis = _colunas_uteis(treino, COLUNAS_FEATURES)
    modelo = _novo_modelo()
    modelo.fit(treino[uteis], treino["alvo"])
    resultado = permutation_importance(
        modelo, treino[uteis], treino["alvo"], n_repeats=8, random_state=42
    )
    importancias = (
        pd.Series(resultado.importances_mean, index=uteis)
        .sort_values(ascending=False)
        .rename("importancia")
        .reset_index()
        .rename(columns={"index": "feature"})
    )
    return modelo, uteis, importancias
