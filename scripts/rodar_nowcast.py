"""Sistema 2 — roda o nowcast completo: dataset, validação LOYO e previsão.

Uso:
    .venv\\Scripts\\python scripts\\rodar_nowcast.py [--ano 2026]

Saídas em data/processed/: nowcast_dataset.csv, nowcast_loyo.csv,
nowcast_metricas.csv, nowcast_importancias.csv, nowcast_previsao.csv
e o boletim em relatorios/.
"""
import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import joblib
import numpy as np
import pandas as pd

from src import config, nowcast


def principal() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ano", type=int, default=2026, help="ano-safra a prever")
    argumentos = parser.parse_args()
    ano_prev = argumentos.ano

    fim_clima = (date.today() - timedelta(days=4)).isoformat()
    print(f"montando dataset (clima ate {fim_clima}; previsao {ano_prev})...", flush=True)
    dataset = nowcast.montar_dataset(fim_clima, ano_previsao=ano_prev)
    n_edrs = dataset["edr_chave"].nunique()
    print(f"dataset: {len(dataset)} linhas | {n_edrs} EDRs | anos {dataset['ano'].min()}–{dataset['ano'].max()}")

    print("\nvalidacao leave-one-year-out...", flush=True)
    loyo, metricas = nowcast.validar_loyo(dataset)
    for chave, valor in metricas.items():
        print(f"  {chave}: {valor:.1f}" if isinstance(valor, float) else f"  {chave}: {valor}")
    ganho = 100 * (1 - metricas["mae_modelo"] / metricas["mae_persistencia"])
    print(f"  ganho vs persistencia: {ganho:.0f}%")

    modelo, importancias = nowcast.treinar_final(dataset)
    print("\nimportancia das features (top 6):")
    print(importancias.head(6).to_string(index=False))

    alvo = dataset[dataset["ano"] == ano_prev].copy()
    if alvo.empty:
        print(f"\nsem linhas para {ano_prev} — confira lags/área.")
        return 1
    alvo["previsto_kg_ha"] = modelo.predict(alvo[nowcast.COLUNAS_FEATURES]).round(0)

    # incerteza empírica: MAE do LOYO por EDR (fallback: MAE global)
    mae_edr = (
        loyo.assign(erro=lambda d: (d["previsto"] - d["rendimento_kg_ha"]).abs())
        .groupby("edr_chave")["erro"]
        .mean()
    )
    alvo["mae_kg_ha"] = alvo["edr_chave"].map(mae_edr).fillna(metricas["mae_modelo"]).round(0)
    alvo["producao_prevista_sc60"] = (
        alvo["previsto_kg_ha"] * alvo["area_ha"] / 60.0
    ).round(0)

    previsao = alvo[
        ["edr_chave", "edr", "ano", "rendimento_a1", "previsto_kg_ha", "mae_kg_ha",
         "area_ha", "producao_prevista_sc60", "anom_florada_pct", "anom_enchimento_pct",
         "tmin_inverno_anterior", "delta_bienal", "razao_preco"]
    ].sort_values("producao_prevista_sc60", ascending=False)

    print(f"\n=== previsao {ano_prev} por EDR ===")
    print(previsao.to_string(index=False))
    total = previsao["producao_prevista_sc60"].sum()
    print(f"\nproducao prevista ({n_edrs} EDRs cobertos): {total/1e6:.2f} M sc")

    pasta = config.PASTA_PROCESSADOS
    pasta.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(pasta / "nowcast_dataset.csv", index=False)
    loyo.to_csv(pasta / "nowcast_loyo.csv", index=False)
    pd.DataFrame([metricas]).to_csv(pasta / "nowcast_metricas.csv", index=False)
    importancias.to_csv(pasta / "nowcast_importancias.csv", index=False)
    previsao.to_csv(pasta / "nowcast_previsao.csv", index=False)
    joblib.dump(modelo, pasta / "modelo_nowcast.joblib")
    print(f"\nsaidas salvas em {pasta}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    raise SystemExit(principal())
