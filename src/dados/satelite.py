"""Sentinel-2 L2A via STAC (earth-search / AWS) — busca de cenas e NDVI.

Sem autenticação: catálogo público da Element 84 sobre o bucket aberto
``sentinel-cogs``. A leitura é feita em janela (só os pixels da área de
interesse) direto por HTTPS — não baixa a cena inteira (~1 GB).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import rasterio
from pystac_client import Client
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

STAC_URL = "https://earth-search.aws.element84.com/v1"
COLECAO = "sentinel-2-l2a"


def buscar_cenas(bbox, inicio, fim, max_nuvens: float = 20.0, max_itens: int | None = None):
    """Itens STAC Sentinel-2 L2A que cobrem o bbox (oeste, sul, leste, norte).

    ``inicio``/``fim`` no formato "AAAA-MM-DD". Ordenados por data crescente.
    """
    catalogo = Client.open(STAC_URL)
    busca = catalogo.search(
        collections=[COLECAO],
        bbox=list(bbox),
        datetime=f"{inicio}/{fim}",
        query={"eo:cloud_cover": {"lt": max_nuvens}},
        max_items=max_itens,
    )
    return sorted(busca.items(), key=lambda item: item.datetime)


def _reflectancia(dn: np.ndarray, item) -> np.ndarray:
    """Converte DN em reflectância BOA, tratando o offset do baseline >= 04.00."""
    dn = dn.astype("float32")
    dn[dn == 0] = np.nan  # 0 = nodata
    deslocamento = 0.0
    if not item.properties.get("earthsearch:boa_offset_applied", False):
        baseline = str(item.properties.get("s2:processing_baseline", "00.00"))
        if baseline >= "04.00":
            deslocamento = -1000.0
    return (dn + deslocamento) / 10000.0


def ndvi_medio(item, bbox) -> float:
    """NDVI médio do bbox (WGS84) em uma cena, lendo apenas a janela necessária."""
    with rasterio.open(item.assets["red"].href) as vermelho:
        limites = transform_bounds("EPSG:4326", vermelho.crs, *bbox)
        janela = from_bounds(*limites, transform=vermelho.transform)
        b04 = _reflectancia(vermelho.read(1, window=janela, boundless=True), item)
    with rasterio.open(item.assets["nir"].href) as infravermelho:
        janela = from_bounds(*limites, transform=infravermelho.transform)
        b08 = _reflectancia(infravermelho.read(1, window=janela, boundless=True), item)
    with np.errstate(invalid="ignore", divide="ignore"):
        ndvi = (b08 - b04) / (b08 + b04)
    return float(np.nanmean(ndvi))


def serie_ndvi(bbox, inicio, fim, max_nuvens: float = 20.0) -> pd.DataFrame:
    """Série temporal de NDVI médio do bbox entre duas datas ("AAAA-MM-DD")."""
    registros = []
    for item in buscar_cenas(bbox, inicio, fim, max_nuvens):
        registros.append(
            {
                "data": item.datetime.date(),
                "ndvi": round(ndvi_medio(item, bbox), 4),
                "nuvens_pct": item.properties.get("eo:cloud_cover"),
                "cena": item.id,
            }
        )
    return pd.DataFrame(registros)
