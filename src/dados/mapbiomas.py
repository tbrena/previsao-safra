"""Máscara de café do MapBiomas (Coleção 9) via COG público.

O MapBiomas publica um GeoTIFF nacional por ano (classe de uso do solo por
pixel de ~30 m) em bucket público. A classe 46 é Café. A leitura é feita em
janela direto por HTTPS — nunca baixamos o raster nacional inteiro.

Cobertura da Coleção 9: 1985–2023. A área de café muda devagar; para anos
recentes sem raster, usar o último disponível.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

URL_BASE = (
    "https://storage.googleapis.com/mapbiomas-public/initiatives/brasil/"
    "collection_9/lclu/coverage/brasil_coverage_{ano}.tif"
)
ANO_MINIMO, ANO_MAXIMO = 1985, 2023
CLASSE_CAFE = 46
METROS_POR_GRAU = 111_320.0


def url_cobertura(ano: int) -> str:
    """URL do raster nacional do ano (limitado à janela da Coleção 9)."""
    ano_efetivo = min(max(int(ano), ANO_MINIMO), ANO_MAXIMO)
    return URL_BASE.format(ano=ano_efetivo)


def ler_mascara_cafe(bbox, ano: int = ANO_MAXIMO):
    """Máscara booleana de café no bbox (oeste, sul, leste, norte).

    Retorna (mascara, transform, crs) na resolução nativa de ~30 m.
    """
    return ler_mascara_classe(bbox, CLASSE_CAFE, ano)


def _hectares_por_pixel(transformacao, latitude_media: float) -> float:
    """Área média de um pixel em hectares, corrigida pela latitude."""
    largura_m = abs(transformacao.a) * METROS_POR_GRAU * np.cos(np.radians(latitude_media))
    altura_m = abs(transformacao.e) * METROS_POR_GRAU
    return largura_m * altura_m / 10_000.0


def ler_mascara_classe(bbox, classe: int, ano: int = ANO_MAXIMO):
    """Máscara booleana de uma classe MapBiomas qualquer no bbox."""
    with rasterio.open(url_cobertura(ano)) as raster:
        limites = transform_bounds("EPSG:4326", raster.crs, *bbox)
        janela = from_bounds(*limites, transform=raster.transform)
        dados = raster.read(1, window=janela, boundless=True, fill_value=0)
        transformacao = raster.window_transform(janela)
        return dados == classe, transformacao, raster.crs


def celulas_cafe(
    edrs,
    ano: int = ANO_MAXIMO,
    celula_graus: float = 0.05,
    minimo_ha: float = 30.0,
    caminho_cache: str | Path | None = None,
) -> pd.DataFrame:
    """Grade de células (~5,5 km) com hectares de café por EDR."""
    return celulas_classe(edrs, CLASSE_CAFE, ano, celula_graus, minimo_ha, caminho_cache)


def celulas_classe(
    edrs,
    classe: int,
    ano: int = ANO_MAXIMO,
    celula_graus: float = 0.05,
    minimo_ha: float = 30.0,
    caminho_cache: str | Path | None = None,
) -> pd.DataFrame:
    """Grade de células (~5,5 km) com hectares de uma classe MapBiomas por EDR.

    ``edrs`` é o GeoDataFrame de :func:`src.dados.geo.carregar_edrs`. Para
    cada EDR, lê a máscara da classe (46 = café, 47 = citros...) do bbox,
    restringe ao polígono e soma os pixels por célula da grade. Células com
    menos de ``minimo_ha`` são descartadas.

    Retorna DataFrame: edr, edr_chave, oeste, sul, leste, norte, cafe_ha
    (nome da coluna de hectares mantido por compatibilidade).
    Com ``caminho_cache``, salva/reusa CSV (recalcula se o arquivo não existir).
    """
    if caminho_cache is not None:
        caminho_cache = Path(caminho_cache)
        if caminho_cache.exists():
            return pd.read_csv(caminho_cache)

    linhas = []
    for _, edr in edrs.iterrows():
        oeste, sul, leste, norte = edr.geometry.bounds
        mascara, transformacao, _ = ler_mascara_classe((oeste, sul, leste, norte), classe, ano)
        dentro = geometry_mask(
            [edr.geometry.__geo_interface__],
            out_shape=mascara.shape,
            transform=transformacao,
            invert=True,
        )
        mascara &= dentro
        total_px = int(mascara.sum())
        if total_px == 0:
            continue
        ha_pixel = _hectares_por_pixel(transformacao, (sul + norte) / 2.0)

        px_por_celula_x = max(1, round(celula_graus / abs(transformacao.a)))
        px_por_celula_y = max(1, round(celula_graus / abs(transformacao.e)))
        linhas_idx, colunas_idx = np.nonzero(mascara)
        celula_y = linhas_idx // px_por_celula_y
        celula_x = colunas_idx // px_por_celula_x
        pares, contagens = np.unique(
            np.stack([celula_y, celula_x]), axis=1, return_counts=True
        )
        for (cy, cx), n_px in zip(pares.T, contagens):
            ha = float(n_px) * ha_pixel
            if ha < minimo_ha:
                continue
            o, n_ = transformacao * (cx * px_por_celula_x, cy * px_por_celula_y)
            l, s = transformacao * ((cx + 1) * px_por_celula_x, (cy + 1) * px_por_celula_y)
            linhas.append(
                {
                    "edr": edr["edr"],
                    "edr_chave": edr["edr_chave"],
                    "oeste": o,
                    "sul": s,
                    "leste": l,
                    "norte": n_,
                    "cafe_ha": round(ha, 1),
                }
            )
        print(f"  {edr['edr']}: {total_px * ha_pixel:,.0f} ha de café", flush=True)

    resultado = pd.DataFrame(linhas)
    if caminho_cache is not None and not resultado.empty:
        caminho_cache.parent.mkdir(parents=True, exist_ok=True)
        resultado.to_csv(caminho_cache, index=False)
    return resultado
