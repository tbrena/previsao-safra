"""Medição de dano por ΔNDVI (Sentinel-2) sobre as áreas de café.

Método: compostos medianos de NDVI antes e depois do evento (janelas em
dias relativos à data), reprojetados a um grid comum de ~44 m, restritos à
máscara de café do MapBiomas. Como a senescência de inverno derruba o NDVI
de toda a paisagem, o Δ mediano das áreas *não-café* é usado como controle:
o dano atribuído ao evento é o excesso de queda do café sobre esse fundo.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_bounds, from_origin
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import from_bounds as janela_de_limites

from .dados import mapbiomas, satelite

RESOLUCAO_PADRAO = 0.0004  # graus ≈ 44 m
MAX_CENAS = 12


def _grade_alvo(bbox, resolucao):
    oeste, sul, leste, norte = bbox
    largura = int(np.ceil((leste - oeste) / resolucao))
    altura = int(np.ceil((norte - sul) / resolucao))
    return (altura, largura), from_origin(oeste, norte, resolucao, resolucao)


def _ndvi_reprojetado(item, bbox, shape_alvo, transform_alvo, resolucao):
    """NDVI de uma cena, lido em janela decimada e reprojetado ao grid alvo."""
    destino = np.full(shape_alvo, np.nan, dtype="float32")
    with rasterio.open(item.assets["red"].href) as vermelho:
        limites = transform_bounds("EPSG:4326", vermelho.crs, *bbox)
        janela = janela_de_limites(*limites, transform=vermelho.transform)
        # fator de decimação p/ ~resolução alvo (usa overviews do COG)
        res_nativa = abs(vermelho.transform.a)
        alvo_m = resolucao * mapbiomas.METROS_POR_GRAU
        fator = max(1, int(round(alvo_m / res_nativa)))
        largura = max(1, int(round(janela.width / fator)))
        altura = max(1, int(round(janela.height / fator)))
        b04 = vermelho.read(
            1, window=janela, out_shape=(altura, largura), boundless=True, fill_value=0
        ).astype("float32")
        limites_janela = vermelho.window_bounds(janela)
        transform_origem = from_bounds(*limites_janela, largura, altura)
        crs_origem = vermelho.crs
    with rasterio.open(item.assets["nir"].href) as infravermelho:
        janela = janela_de_limites(*limites, transform=infravermelho.transform)
        b08 = infravermelho.read(
            1, window=janela, out_shape=(altura, largura), boundless=True, fill_value=0
        ).astype("float32")

    b04[b04 == 0] = np.nan
    b08[b08 == 0] = np.nan
    with np.errstate(invalid="ignore", divide="ignore"):
        ndvi = (b08 - b04) / (b08 + b04)
    reproject(
        ndvi,
        destino,
        src_transform=transform_origem,
        src_crs=crs_origem,
        dst_transform=transform_alvo,
        dst_crs="EPSG:4326",
        src_nodata=np.nan,
        dst_nodata=np.nan,
        resampling=Resampling.bilinear,
    )
    return destino


def compor_ndvi(
    bbox,
    inicio: str,
    fim: str,
    resolucao: float = RESOLUCAO_PADRAO,
    max_nuvens: float = 20.0,
    max_cenas: int = MAX_CENAS,
):
    """Composto mediano de NDVI do período no grid alvo (EPSG:4326).

    Retorna (ndvi_mediano, transform, n_cenas). Mediana entre cenas descarta
    nuvens residuais e monta o mosaico entre tiles naturalmente.
    """
    itens = satelite.buscar_cenas(bbox, inicio, fim, max_nuvens=max_nuvens)
    if not itens:
        raise RuntimeError(f"nenhuma cena Sentinel-2 em {inicio}/{fim} para {bbox}")
    itens = sorted(itens, key=lambda i: i.properties.get("eo:cloud_cover", 100))[:max_cenas]
    shape_alvo, transform_alvo = _grade_alvo(bbox, resolucao)
    pilha = [
        _ndvi_reprojetado(item, bbox, shape_alvo, transform_alvo, resolucao)
        for item in itens
    ]
    with warnings.catch_warnings():
        # pixels sem nenhuma cena válida viram NaN em silêncio
        warnings.simplefilter("ignore", category=RuntimeWarning)
        mediana = np.nanmedian(np.stack(pilha), axis=0)
    return mediana, transform_alvo, len(itens)


def _mascara_cafe_no_grid(bbox, shape_alvo, transform_alvo, ano):
    mascara30, transform30, crs30 = mapbiomas.ler_mascara_cafe(bbox, ano)
    destino = np.zeros(shape_alvo, dtype="uint8")
    reproject(
        mascara30.astype("uint8"),
        destino,
        src_transform=transform30,
        src_crs=crs30,
        dst_transform=transform_alvo,
        dst_crs="EPSG:4326",
        resampling=Resampling.nearest,
    )
    return destino.astype(bool)


def dano_evento(
    bbox,
    data_evento: str,
    ano_mascara: int | None = None,
    janela_antes: tuple[int, int] = (-35, -3),
    janela_depois: tuple[int, int] = (7, 45),
    resolucao: float = RESOLUCAO_PADRAO,
    max_nuvens: float = 20.0,
) -> dict:
    """Estatísticas de ΔNDVI do café (com controle não-café) em torno do evento.

    Retorna dict com NDVI antes/depois, Δ mediano do café e do fundo, o
    excesso de queda e o % da área de café por faixa de queda (já descontado
    o fundo). ``pct_area_afetada`` usa a faixa ≤ −0,05 de excesso.
    """
    evento = pd.Timestamp(data_evento)
    if ano_mascara is None:
        ano_mascara = evento.year
    a0 = (evento + pd.Timedelta(days=janela_antes[0])).date().isoformat()
    a1 = (evento + pd.Timedelta(days=janela_antes[1])).date().isoformat()
    d0 = (evento + pd.Timedelta(days=janela_depois[0])).date().isoformat()
    d1 = (evento + pd.Timedelta(days=janela_depois[1])).date().isoformat()

    antes, transform_alvo, n_antes = compor_ndvi(bbox, a0, a1, resolucao, max_nuvens)
    depois, _, n_depois = compor_ndvi(bbox, d0, d1, resolucao, max_nuvens)
    cafe = _mascara_cafe_no_grid(bbox, antes.shape, transform_alvo, ano_mascara)

    delta = depois - antes
    validos = ~np.isnan(delta)
    d_cafe = delta[cafe & validos]
    d_fundo = delta[(~cafe) & validos]
    if d_cafe.size == 0:
        raise RuntimeError("nenhum pixel de café válido no bbox")

    fundo_mediano = float(np.median(d_fundo)) if d_fundo.size else 0.0
    excesso = d_cafe - fundo_mediano
    faixas = {
        "pct_queda_leve": float(100 * np.mean(excesso <= -0.05)),
        "pct_queda_moderada": float(100 * np.mean(excesso <= -0.10)),
        "pct_queda_forte": float(100 * np.mean(excesso <= -0.15)),
    }
    return {
        "data_evento": str(evento.date()),
        "janela_antes": f"{a0} a {a1} ({n_antes} cenas)",
        "janela_depois": f"{d0} a {d1} ({n_depois} cenas)",
        "px_cafe": int(d_cafe.size),
        "ndvi_cafe_antes": round(float(np.nanmedian(antes[cafe & validos])), 4),
        "ndvi_cafe_depois": round(float(np.nanmedian(depois[cafe & validos])), 4),
        "delta_cafe_mediano": round(float(np.median(d_cafe)), 4),
        "delta_fundo_mediano": round(fundo_mediano, 4),
        "excesso_mediano": round(float(np.median(excesso)), 4),
        "pct_area_afetada": round(faixas["pct_queda_leve"], 1),
        **{k: round(v, 1) for k, v in faixas.items()},
    }


def dano_geada_edr(
    edr_chave: str,
    data_evento: str,
    celulas: pd.DataFrame,
    **opcoes,
) -> dict:
    """Dano do evento no EDR, usando o bbox das células de café dele."""
    sel = celulas[celulas["edr_chave"] == edr_chave.upper()]
    if sel.empty:
        raise ValueError(f"sem células de café para {edr_chave!r}")
    bbox = (
        float(sel["oeste"].min()),
        float(sel["sul"].min()),
        float(sel["leste"].max()),
        float(sel["norte"].max()),
    )
    resultado = dano_evento(bbox, data_evento, **opcoes)
    resultado["edr_chave"] = edr_chave.upper()
    resultado["cafe_ha_celulas"] = float(sel["cafe_ha"].sum())
    return resultado
