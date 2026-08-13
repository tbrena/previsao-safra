"""Tradução do dano NDVI em perda de produção (sacas) e valor (R$).

Nota de calibração (importante): a regressão linear dano→perda ajustada nos
5 EDRs da geada de 2021 não fecha (k≈0). O rendimento do ano seguinte é
dominado por fatores que o ΔNDVI do evento não vê — seca acumulada, poda
pós-geada (esqueletamento), fase bienal local. Por isso a v1 usa classes
agronômicas com faixas conservadoras e incerteza explícita de ±50%; o refino
estatístico é papel do modelo do Sistema 2, com o dano como covariável.
"""
from __future__ import annotations

import pandas as pd

# Fundo medido no placebo (Franca, jul/2019, sem geada): % da área de café
# que cai nessas faixas num inverno normal.
PLACEBO = {"leve": 13.9, "moderada": 5.6, "forte": 2.8}

# Perda de produção assumida para a área em cada classe líquida de dano
# (fração da produção daquela área na safra seguinte).
PERDA_POR_CLASSE = {"forte": 0.70, "moderada": 0.35, "leve": 0.15}
INCERTEZA = 0.50  # faixa de ±50% sobre a estimativa central


def perda_percentual(resultado_dano: dict) -> dict:
    """Perda central e faixa (% da produção do EDR) a partir do dano medido.

    As faixas do resultado são cumulativas (leve ⊇ moderada ⊇ forte); aqui
    viram bandas exclusivas, descontado o fundo do placebo por banda.
    """
    forte = resultado_dano["pct_queda_forte"]
    moderada = resultado_dano["pct_queda_moderada"] - forte
    leve = resultado_dano["pct_queda_leve"] - resultado_dano["pct_queda_moderada"]

    placebo_forte = PLACEBO["forte"]
    placebo_moderada = PLACEBO["moderada"] - PLACEBO["forte"]
    placebo_leve = PLACEBO["leve"] - PLACEBO["moderada"]

    bandas_liquidas = {
        "forte": max(0.0, forte - placebo_forte),
        "moderada": max(0.0, moderada - placebo_moderada),
        "leve": max(0.0, leve - placebo_leve),
    }
    central = sum(
        bandas_liquidas[classe] * PERDA_POR_CLASSE[classe] for classe in bandas_liquidas
    )
    return {
        "bandas_liquidas_pp": {k: round(v, 1) for k, v in bandas_liquidas.items()},
        "perda_pct_central": round(central, 1),
        "perda_pct_faixa": (
            round(central * (1 - INCERTEZA), 1),
            round(central * (1 + INCERTEZA), 1),
        ),
    }


def valorar_perda(
    perda: dict,
    producao_base_sc: float,
    preco_sc: float,
) -> dict:
    """Sacas e R$ da perda estimada, dada a produção-base do EDR e o preço."""
    central = perda["perda_pct_central"] / 100.0
    minimo, maximo = (p / 100.0 for p in perda["perda_pct_faixa"])
    return {
        "producao_base_sc": round(producao_base_sc),
        "sacas_perdidas": round(producao_base_sc * central),
        "sacas_faixa": (round(producao_base_sc * minimo), round(producao_base_sc * maximo)),
        "valor_reais": round(producao_base_sc * central * preco_sc),
        "valor_faixa": (
            round(producao_base_sc * minimo * preco_sc),
            round(producao_base_sc * maximo * preco_sc),
        ),
    }


def tabela_evento(
    resultados_dano: list[dict],
    producao_base: pd.DataFrame,
    preco_sc: float,
    eventos_clima: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Tabela final do evento por EDR.

    ``producao_base``: DataFrame com edr_chave e producao_sc60 (safra base,
    tipicamente o último ano de carga equivalente do IEA). ``preco_sc`` em
    R$/sc 60 kg. ``eventos_clima`` (opcional) anexa o T2M_MIN por EDR.
    """
    base = producao_base.set_index("edr_chave")["producao_sc60"]
    linhas = []
    for resultado in resultados_dano:
        chave = resultado["edr_chave"]
        perda = perda_percentual(resultado)
        valor = valorar_perda(perda, float(base.get(chave, 0.0)), preco_sc)
        linha = {
            "edr": chave,
            "pct_area_forte": resultado["pct_queda_forte"],
            "pct_area_moderada": resultado["pct_queda_moderada"],
            "perda_pct": perda["perda_pct_central"],
            "perda_pct_min": perda["perda_pct_faixa"][0],
            "perda_pct_max": perda["perda_pct_faixa"][1],
            **valor,
        }
        if eventos_clima is not None and not eventos_clima.empty:
            sel = eventos_clima[eventos_clima["edr_chave"] == chave]
            if not sel.empty:
                linha["t2m_min"] = float(sel["t2m_min"].min())
        linhas.append(linha)
    return pd.DataFrame(linhas).sort_values("sacas_perdidas", ascending=False).reset_index(drop=True)
