"""Série de NDVI por EDR nas janelas fenológicas — feature do nowcast.

Estratégia leve, sem cadastro: para cada EDR, amostramos a **célula de café
mais densa** (do MapBiomas, ~5,5 km) — a mesma caixa todos os anos, então a
*anomalia* interanual é comparável mesmo sem cobrir o EDR inteiro. Em cada
janela (florada set–nov, enchimento dez–mar) lemos até 3 cenas Sentinel-2 de
menor nebulosidade, decimadas a ~160 m via overviews dos COGs (leituras de
poucos KB), e usamos a média.

Cobertura: 2017+ (arquivo L2A na AWS). Anos anteriores ficam NaN — o modelo
(HistGradientBoosting) aceita ausentes nativamente.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

from . import satelite

RESOLUCAO_ALVO_M = 160.0
MAX_CENAS = 3

# janela -> (inicio, fim) relativos ao ano-safra A (colheita mai–set de A)
JANELAS = {
    "florada": lambda ano: (f"{ano - 1}-09-01", f"{ano - 1}-11-30"),
    "enchimento": lambda ano: (f"{ano - 1}-12-01", f"{ano}-03-31"),
}


def _ndvi_medio_cena(item, bbox) -> float:
    """NDVI médio do bbox em uma cena, leitura decimada (~160 m)."""
    with rasterio.open(item.assets["red"].href) as vermelho:
        limites = transform_bounds("EPSG:4326", vermelho.crs, *bbox)
        janela = from_bounds(*limites, transform=vermelho.transform)
        fator = max(1, int(round(RESOLUCAO_ALVO_M / abs(vermelho.transform.a))))
        largura = max(1, int(round(janela.width / fator)))
        altura = max(1, int(round(janela.height / fator)))
        b04 = vermelho.read(
            1, window=janela, out_shape=(altura, largura), boundless=True, fill_value=0
        ).astype("float32")
    with rasterio.open(item.assets["nir"].href) as infravermelho:
        janela = from_bounds(*limites, transform=infravermelho.transform)
        b08 = infravermelho.read(
            1, window=janela, out_shape=(altura, largura), boundless=True, fill_value=0
        ).astype("float32")
    b04[b04 == 0] = np.nan
    b08[b08 == 0] = np.nan
    with np.errstate(invalid="ignore", divide="ignore"):
        ndvi = (b08 - b04) / (b08 + b04)
    return float(np.nanmean(ndvi))


def ndvi_janela(bbox, inicio: str, fim: str, max_nuvens: float = 30.0) -> tuple[float, int]:
    """(NDVI médio, nº de cenas usadas) do bbox no período; (nan, 0) se vazio."""
    itens = satelite.buscar_cenas(bbox, inicio, fim, max_nuvens=max_nuvens)
    if not itens:
        return float("nan"), 0
    itens = sorted(itens, key=lambda i: i.properties.get("eo:cloud_cover", 100))[:MAX_CENAS]
    valores = []
    for item in itens:
        try:
            valor = _ndvi_medio_cena(item, bbox)
            if np.isfinite(valor):
                valores.append(valor)
        except Exception:
            continue
    if not valores:
        return float("nan"), 0
    return float(np.mean(valores)), len(valores)


def caixas_por_edr(celulas: pd.DataFrame) -> dict[str, tuple]:
    """Célula de café mais densa de cada EDR → bbox (oeste, sul, leste, norte)."""
    caixas = {}
    for chave, grupo in celulas.groupby("edr_chave"):
        melhor = grupo.loc[grupo["cafe_ha"].idxmax()]
        caixas[chave] = (
            float(melhor["oeste"]),
            float(melhor["sul"]),
            float(melhor["leste"]),
            float(melhor["norte"]),
        )
    return caixas


def gerar_serie(
    celulas: pd.DataFrame,
    edrs_chave: list[str],
    anos: range,
    caminho_cache: str | Path,
) -> pd.DataFrame:
    """Gera/atualiza o CSV de NDVI por (EDR, ano, janela) — incremental.

    Só busca combinações ausentes do cache; reexecutar é barato.
    """
    from concurrent.futures import ThreadPoolExecutor

    caminho_cache = Path(caminho_cache)
    if caminho_cache.exists():
        serie = pd.read_csv(caminho_cache)
    else:
        serie = pd.DataFrame(columns=["edr_chave", "ano", "janela", "ndvi", "n_cenas"])
    existentes = set(zip(serie["edr_chave"], serie["ano"], serie["janela"]))
    caixas = caixas_por_edr(celulas)

    def _uma(tarefa):
        chave, bbox, ano, nome = tarefa
        inicio, fim = JANELAS[nome](ano)
        valor, n_cenas = ndvi_janela(bbox, inicio, fim)
        rotulo = f"{valor:.3f} ({n_cenas} cenas)" if np.isfinite(valor) else "sem cena"
        print(f"  {chave} {ano} {nome}: {rotulo}", flush=True)
        return {
            "edr_chave": chave, "ano": ano, "janela": nome,
            "ndvi": round(valor, 4) if np.isfinite(valor) else np.nan,
            "n_cenas": n_cenas,
        }

    for chave in edrs_chave:
        if chave not in caixas:
            continue
        bbox = caixas[chave]
        pendentes = [
            (chave, bbox, ano, nome)
            for ano in anos
            for nome in JANELAS
            if (chave, ano, nome) not in existentes
        ]
        if not pendentes:
            continue
        # rede é o gargalo (abertura de COGs remotos) — 8 threads ≈ 8x
        with ThreadPoolExecutor(max_workers=8) as executor:
            novas = list(executor.map(_uma, pendentes))
        # salva por EDR (retomável se interromper)
        serie = pd.concat([serie, pd.DataFrame(novas)], ignore_index=True)
        caminho_cache.parent.mkdir(parents=True, exist_ok=True)
        serie.to_csv(caminho_cache, index=False)
    return serie


def anomalias(serie: pd.DataFrame) -> pd.DataFrame:
    """Anomalia de NDVI por (EDR, ano, janela): valor − média do próprio EDR.

    Retorna formato largo: edr_chave, ano, anom_ndvi_florada, anom_ndvi_enchimento.
    """
    com_dado = serie.dropna(subset=["ndvi"]).copy()
    medias = com_dado.groupby(["edr_chave", "janela"])["ndvi"].transform("mean")
    com_dado["anomalia"] = com_dado["ndvi"] - medias
    largo = com_dado.pivot_table(
        index=["edr_chave", "ano"], columns="janela", values="anomalia", aggfunc="first"
    ).reset_index()
    largo.columns.name = None
    return largo.rename(
        columns={"florada": "anom_ndvi_florada", "enchimento": "anom_ndvi_enchimento"}
    )
