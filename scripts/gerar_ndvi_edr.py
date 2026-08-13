"""Gera a série de NDVI por EDR (janelas florada/enchimento, 2017–2026).

Uso:
    .venv\\Scripts\\python scripts\\gerar_ndvi_edr.py

Incremental: só busca o que falta em data/processed/ndvi_edr.csv.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from src import config, nowcast
from src.dados import iea, ndvi_edr


def principal() -> int:
    celulas = pd.read_csv(config.CACHE_CELULAS_CAFE)
    cafe = iea.cafe_edr(config.PASTA_IEA)
    medias = cafe.groupby("edr_chave")["area_producao_ha"].mean()
    elegiveis = sorted(medias[medias >= nowcast.AREA_MINIMA_HA].index)

    print(f"NDVI por EDR: {len(elegiveis)} EDRs, anos-safra 2017–2026, 2 janelas")
    serie = ndvi_edr.gerar_serie(
        celulas, elegiveis, range(2017, 2027), config.CACHE_NDVI_EDR
    )
    validos = serie.dropna(subset=["ndvi"])
    print(f"\ntotal: {len(serie)} combinações | com dado: {len(validos)}")
    print(f"cache: {config.CACHE_NDVI_EDR}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    raise SystemExit(principal())
