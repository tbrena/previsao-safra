"""Gera a série de NDVI por EDR (janelas florada/enchimento, 2017–2026).

Uso:
    .venv\\Scripts\\python scripts\\gerar_ndvi_edr.py [--cultura cafe|laranja]

Incremental: só busca o que falta no cache da cultura.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from src import config, nowcast
from src.dados import iea, ndvi_edr


def principal() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cultura", default="cafe",
                        choices=[c for c, cfg in nowcast.CULTURAS.items() if cfg["ndvi"]])
    argumentos = parser.parse_args()
    cfg = nowcast.CULTURAS[argumentos.cultura]

    celulas = pd.read_csv(config.PASTA_PROCESSADOS / cfg["celulas"])
    dados = iea.producao_edr(config.PASTA_IEA, cfg["produtos"], cfg["kg_por_unidade"])
    medias = dados.groupby("edr_chave")[cfg["capacidade"]].mean()
    elegiveis = sorted(medias[medias >= cfg["capacidade_minima"]].index)

    cache = config.PASTA_PROCESSADOS / cfg["ndvi"]
    print(f"[{cfg['rotulo']}] NDVI: {len(elegiveis)} EDRs, anos-safra 2017–2026, 2 janelas")
    serie = ndvi_edr.gerar_serie(celulas, elegiveis, range(2017, 2027), cache)
    validos = serie.dropna(subset=["ndvi"])
    print(f"\ntotal: {len(serie)} combinações | com dado: {len(validos)}")
    print(f"cache: {cache}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    raise SystemExit(principal())
