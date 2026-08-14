"""Placar público: previsões congeladas e confronto com o realizado.

Regras do jogo (a credibilidade do projeto depende delas):

1. Uma previsão congelada recebe data, commit e detalhe por EDR em
   ``previsoes/`` — e **nunca mais é alterada** (append-only).
2. Quando o levantamento oficial (IEA) do ano-safra aparece nos dados, o
   confronto é calculado automaticamente: erro na produção total, erro médio
   por EDR e comparação com o baseline de persistência congelado junto.
3. Acertos e erros ficam expostos igualmente. Previsão sem placar é opinião.
"""
from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from . import config, nowcast

PASTA_PREVISOES = config.RAIZ / "previsoes"
PASTA_DETALHE = PASTA_PREVISOES / "detalhe"
CAMINHO_REGISTRO = PASTA_PREVISOES / "registro.csv"

COLUNAS_REGISTRO = [
    "id", "data_congelamento", "commit", "cultura", "ano_safra", "n_edrs",
    "producao_prevista_unid", "unidade_producao", "producao_prevista_t",
    "mae_validacao", "unidade_alvo",
]


def _commit_atual() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=config.RAIZ, text=True
        ).strip()
    except Exception:
        return "desconhecido"


def carregar_registro() -> pd.DataFrame:
    if CAMINHO_REGISTRO.exists():
        return pd.read_csv(CAMINHO_REGISTRO)
    return pd.DataFrame(columns=COLUNAS_REGISTRO)


def congelar(cultura: str) -> str | None:
    """Congela a previsão corrente da cultura. Retorna o id (ou None se já existe hoje)."""
    cfg = nowcast.CULTURAS[cultura]
    caminho_previsao = config.PASTA_PROCESSADOS / f"nowcast_{cultura}_previsao.csv"
    caminho_metricas = config.PASTA_PROCESSADOS / f"nowcast_{cultura}_metricas.csv"
    if not caminho_previsao.exists():
        raise FileNotFoundError(f"rode antes: scripts/rodar_nowcast.py --cultura {cultura}")

    previsao = pd.read_csv(caminho_previsao)
    metricas = pd.read_csv(caminho_metricas).iloc[0] if caminho_metricas.exists() else None
    ano_safra = int(previsao["ano"].iloc[0])
    hoje = date.today().isoformat()
    id_previsao = f"{cultura}_{ano_safra}_{hoje}"

    registro = carregar_registro()
    if id_previsao in set(registro["id"]):
        return None  # já congelada hoje — congelamento é imutável

    PASTA_DETALHE.mkdir(parents=True, exist_ok=True)
    colunas_detalhe = [
        "edr_chave", "edr", "ano", "previsto", "mae", "rendimento_a1",
        "capacidade", "producao_prevista_unid", "producao_prevista_t",
    ]
    previsao[[c for c in colunas_detalhe if c in previsao.columns]].to_csv(
        PASTA_DETALHE / f"{id_previsao}.csv", index=False
    )

    linha = {
        "id": id_previsao,
        "data_congelamento": hoje,
        "commit": _commit_atual(),
        "cultura": cultura,
        "ano_safra": ano_safra,
        "n_edrs": int(previsao["edr_chave"].nunique()),
        "producao_prevista_unid": float(previsao["producao_prevista_unid"].sum()),
        "unidade_producao": cfg["unidade_producao"],
        "producao_prevista_t": float(previsao["producao_prevista_t"].sum()),
        "mae_validacao": float(metricas["mae_modelo"]) if metricas is not None else np.nan,
        "unidade_alvo": cfg["unidade_alvo"],
    }
    registro = pd.concat([registro, pd.DataFrame([linha])], ignore_index=True)
    registro.to_csv(CAMINHO_REGISTRO, index=False)
    return id_previsao


def confrontar() -> pd.DataFrame:
    """Registro enriquecido com o realizado (quando o levantamento já saiu).

    Colunas adicionadas: status, producao_real_unid, erro_producao_pct,
    mae_realizado (no alvo, por EDR), mae_persistencia_realizado e
    modelo_venceu (bool) — NaN enquanto o ano-safra não tem dado oficial.
    """
    registro = carregar_registro()
    if registro.empty:
        return registro

    extras = []
    memo_dados: dict[str, pd.DataFrame] = {}
    for _, linha in registro.iterrows():
        cfg = nowcast.CULTURAS[linha["cultura"]]
        detalhe = pd.read_csv(PASTA_DETALHE / f"{linha['id']}.csv")
        if linha["cultura"] not in memo_dados:
            try:
                from .dados import iea

                memo_dados[linha["cultura"]] = iea.producao_edr(
                    config.PASTA_IEA, cfg["produtos"], cfg["kg_por_unidade"]
                )
            except Exception:
                memo_dados[linha["cultura"]] = pd.DataFrame()
        dados = memo_dados[linha["cultura"]]
        realizado = (
            dados[(dados["ano"] == linha["ano_safra"])].dropna(subset=[cfg["alvo"]])
            if not dados.empty
            else pd.DataFrame()
        )
        if realizado.empty:
            extras.append({"status": "aguardando levantamento"})
            continue

        junto = detalhe.merge(
            realizado[["edr_chave", cfg["alvo"], "producao_unid"]],
            on="edr_chave",
            how="inner",
        ).rename(columns={cfg["alvo"]: "alvo_real"})
        if junto.empty:
            extras.append({"status": "aguardando levantamento"})
            continue

        producao_real = float(junto["producao_unid"].sum())
        extras.append(
            {
                "status": "confrontado",
                "producao_real_unid": producao_real,
                "erro_producao_pct": round(
                    100 * (linha["producao_prevista_unid"] - producao_real) / producao_real, 1
                ),
                "mae_realizado": round(float((junto["previsto"] - junto["alvo_real"]).abs().mean()), 3),
                "mae_persistencia_realizado": round(
                    float((junto["rendimento_a1"] - junto["alvo_real"]).abs().mean()), 3
                ),
                "modelo_venceu": bool(
                    (junto["previsto"] - junto["alvo_real"]).abs().mean()
                    <= (junto["rendimento_a1"] - junto["alvo_real"]).abs().mean()
                ),
            }
        )
    return pd.concat([registro, pd.DataFrame(extras)], axis=1)
