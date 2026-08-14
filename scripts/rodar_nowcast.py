"""Sistema 2 — roda o nowcast de uma cultura: dataset, validação e previsão.

Uso:
    .venv\\Scripts\\python scripts\\rodar_nowcast.py [--cultura cafe] [--ano 2026]

Culturas: cafe | laranja | amendoim | milho_safrinha

Saídas em data/processed/: nowcast_{cultura}_dataset.csv, _loyo.csv,
_metricas.csv, _importancias.csv, _previsao.csv e modelo_{cultura}.joblib.
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
    parser.add_argument("--cultura", default="cafe", choices=sorted(nowcast.CULTURAS))
    parser.add_argument("--ano", type=int, default=2026, help="ano-safra a prever")
    argumentos = parser.parse_args()
    cultura, ano_prev = argumentos.cultura, argumentos.ano
    cfg = nowcast.CULTURAS[cultura]

    fim_clima = (date.today() - timedelta(days=4)).isoformat()
    print(f"[{cfg['rotulo']}] montando dataset (clima ate {fim_clima}; previsao {ano_prev})...", flush=True)
    dataset = nowcast.montar_dataset(fim_clima, cultura, ano_previsao=ano_prev)
    n_edrs = dataset["edr_chave"].nunique()
    print(f"dataset: {len(dataset)} linhas | {n_edrs} EDRs | anos {dataset['ano'].min()}–{dataset['ano'].max()}"
          f" | alvo: {cfg['alvo']} ({cfg['unidade_alvo']})")

    print("\nvalidacao leave-one-year-out...", flush=True)
    loyo, metricas = nowcast.validar_loyo(dataset)
    erro_abs = (loyo["previsto"] - loyo["alvo"]).abs()
    metricas["mae_modelo_pond"] = float(np.average(erro_abs, weights=loyo["capacidade"]))
    com_a2 = loyo.dropna(subset=["rendimento_a2"])
    metricas["mae_lag2_pond"] = float(
        np.average((com_a2["rendimento_a2"] - com_a2["alvo"]).abs(), weights=com_a2["capacidade"])
    )
    for chave, valor in metricas.items():
        print(f"  {chave}: {valor:.2f}" if isinstance(valor, float) else f"  {chave}: {valor}")
    ganho = 100 * (1 - metricas["mae_modelo"] / metricas["mae_persistencia"])
    ganho_pond = 100 * (1 - metricas["mae_modelo_pond"] / metricas["mae_lag2_pond"])
    print(f"  ganho vs persistencia: {ganho:.0f}% | vs lag-2 ponderado por capacidade: {ganho_pond:+.0f}%")

    modelo, uteis, importancias = nowcast.treinar_final(dataset)
    print("\nimportancia das features (top 6):")
    print(importancias.head(6).to_string(index=False))

    alvo = dataset[dataset["ano"] == ano_prev].copy()
    if alvo.empty:
        print(f"\nsem linhas para {ano_prev}.")
        return 1
    alvo["previsto"] = modelo.predict(alvo[uteis]).round(3)

    mae_edr = (
        loyo.assign(erro=lambda d: (d["previsto"] - d["alvo"]).abs())
        .groupby("edr_chave")["erro"]
        .mean()
    )
    alvo["mae"] = alvo["edr_chave"].map(mae_edr).fillna(metricas["mae_modelo"]).round(3)
    if cfg["alvo"] == "rendimento_kg_ha":
        alvo["producao_prevista_unid"] = (
            alvo["previsto"] * alvo["capacidade"] / cfg["kg_por_unidade"]
        ).round(0)
    else:  # alvo por pé (laranja): unid/pé × pés
        alvo["producao_prevista_unid"] = (alvo["previsto"] * alvo["capacidade"]).round(0)
    alvo["producao_prevista_t"] = (
        alvo["producao_prevista_unid"] * cfg["kg_por_unidade"] / 1000.0
    ).round(0)

    previsao = alvo[
        ["edr_chave", "edr", "ano", "rendimento_a1", "previsto", "mae", "capacidade",
         "producao_prevista_unid", "producao_prevista_t",
         "anom_critica_pct", "anom_secundaria_pct", "tmin_fria", "delta_bienal", "razao_preco"]
    ].sort_values("producao_prevista_unid", ascending=False)

    print(f"\n=== previsao {ano_prev} — {cfg['rotulo']} (alvo em {cfg['unidade_alvo']};"
          f" producao em {cfg['unidade_producao']}) ===")
    print(previsao.to_string(index=False))
    total_unid = previsao["producao_prevista_unid"].sum()
    total_t = previsao["producao_prevista_t"].sum()
    print(f"\nproducao prevista ({n_edrs} EDRs): {total_unid/1e6:.2f} M {cfg['unidade_producao']}"
          f" = {total_t/1e3:,.0f} mil t")

    pasta = config.PASTA_PROCESSADOS
    pasta.mkdir(parents=True, exist_ok=True)
    prefixo = f"nowcast_{cultura}"
    dataset.to_csv(pasta / f"{prefixo}_dataset.csv", index=False)
    loyo.to_csv(pasta / f"{prefixo}_loyo.csv", index=False)
    metricas["cultura"] = cultura
    metricas["unidade_alvo"] = cfg["unidade_alvo"]
    metricas["unidade_producao"] = cfg["unidade_producao"]
    pd.DataFrame([metricas]).to_csv(pasta / f"{prefixo}_metricas.csv", index=False)
    importancias.to_csv(pasta / f"{prefixo}_importancias.csv", index=False)
    previsao.to_csv(pasta / f"{prefixo}_previsao.csv", index=False)
    joblib.dump(modelo, pasta / f"modelo_{cultura}.joblib")
    print(f"\nsaidas salvas em {pasta} (prefixo {prefixo}_)")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    raise SystemExit(principal())
