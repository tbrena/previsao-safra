"""Camadas geográficas: EDRs da CATI (2022) e Regiões Administrativas de SP.

TopoJSONs em ``data/raw/shapes/``:

- ``edrs_cati_2022.topojson`` — 40 polígonos, um por CATI Regional/EDR
  (municípios dissolvidos por regional). As propriedades de nome/código IBGE
  herdam o primeiro município de cada grupo — usar somente a coluna
  ``*_CATI_REGIONAL``, que traz o nome do EDR.
- ``sp_regioes_administrativas.topojson`` — 16 Regiões Administrativas de SP.

Os nomes de EDR são normalizados para caixa alta, casando com os exports do
IEA (``src/dados/iea.py``).
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd

from .util import chave_regiao


def carregar_edrs(caminho: str | Path) -> gpd.GeoDataFrame:
    """GeoDataFrame com colunas ``edr`` (rótulo), ``edr_chave`` e ``geometry``.

    Junções com outras fontes (IEA etc.) devem usar ``edr_chave``.
    """
    gdf = gpd.read_file(caminho)
    coluna = next(c for c in gdf.columns if c.endswith("CATI_REGIONAL"))
    gdf = gdf[[coluna, "geometry"]].rename(columns={coluna: "edr"})
    gdf["edr"] = gdf["edr"].str.strip()
    gdf["edr_chave"] = gdf["edr"].map(chave_regiao)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    return gdf.sort_values("edr")[["edr", "edr_chave", "geometry"]].reset_index(drop=True)


def carregar_ras(caminho: str | Path) -> gpd.GeoDataFrame:
    """Regiões Administrativas de SP com colunas ``ra`` e ``geometry``."""
    gdf = gpd.read_file(caminho)
    gdf = gdf[["RA", "geometry"]].rename(columns={"RA": "ra"})
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    return gdf.sort_values("ra").reset_index(drop=True)


def bbox(gdf: gpd.GeoDataFrame, nome: str) -> tuple[float, float, float, float]:
    """Bounding box (oeste, sul, leste, norte) de uma região, p/ busca STAC.

    ``nome`` é comparado de forma normalizada (aceita acentos/hífens/caixa).
    """
    chave = chave_regiao(nome)
    coluna = next(c for c in ("edr_chave", "edr", "ra") if c in gdf.columns)
    sel = gdf[gdf[coluna].map(chave_regiao) == chave]
    if sel.empty:
        raise ValueError(f"{nome!r} não encontrado em {sorted(gdf[coluna].unique())}")
    oeste, sul, leste, norte = sel.total_bounds
    return (float(oeste), float(sul), float(leste), float(norte))
