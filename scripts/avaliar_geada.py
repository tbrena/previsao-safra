"""Sistema 1 — avaliação rápida de geada no café paulista.

Pipeline: detecção no clima (NASA POWER) → dano por ΔNDVI (Sentinel-2 sobre
as células de café MapBiomas) → perda por classes agronômicas → sacas e R$
(produção IEA × preço recebido) → relatório markdown.

Uso:
    python scripts/avaliar_geada.py                          # varre os últimos 45 dias
    python scripts/avaliar_geada.py --inicio 2021-07-15 --fim 2021-08-05
    python scripts/avaliar_geada.py --somente-clima          # sem NDVI (rápido)
"""
import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from src import config, dano, eventos, perda
from src.dados import geo, iea

MINIMO_CAFE_HA = 1000.0  # só avalia EDRs com café relevante
SEVERIDADES_NDVI = {"moderada", "severa", "extrema"}


def principal() -> int:
    parser = argparse.ArgumentParser(description="Avaliação rápida de geada no café de SP")
    parser.add_argument("--inicio", default=None, help="AAAA-MM-DD (padrão: 45 dias atrás)")
    parser.add_argument("--fim", default=None, help="AAAA-MM-DD (padrão: hoje)")
    parser.add_argument("--somente-clima", action="store_true", help="pula a medição NDVI")
    argumentos = parser.parse_args()

    fim = argumentos.fim or date.today().isoformat()
    inicio = argumentos.inicio or (date.fromisoformat(fim) - timedelta(days=45)).isoformat()

    celulas = pd.read_csv(config.CACHE_CELULAS_CAFE)
    cafe_por_edr = celulas.groupby("edr_chave")["cafe_ha"].sum()
    relevantes = set(cafe_por_edr[cafe_por_edr >= MINIMO_CAFE_HA].index)
    edrs = geo.carregar_edrs(config.CAMINHO_EDRS)
    edrs = edrs[edrs["edr_chave"].isin(relevantes)]

    print(f"varredura de geada {inicio} a {fim} em {len(edrs)} EDRs cafeeiros...")
    clima = eventos.geadas_por_edr(edrs, inicio, fim)
    if clima.empty:
        print("nenhum dia com T2M_MIN <= 6 C — sem risco de geada no período.")
        return 0
    print(clima.to_string(index=False))

    alvo = clima[clima["severidade"].isin(SEVERIDADES_NDVI)]
    if alvo.empty:
        print("\neventos apenas na faixa 'atenção' — dano relevante improvável; NDVI não medido.")
        return 0
    if argumentos.somente_clima:
        print(f"\n--somente-clima: {alvo['edr_chave'].nunique()} EDR(s) elegíveis para medição NDVI.")
        return 0

    hoje = date.today()
    resultados, pulados = [], []
    for chave, grupo in alvo.groupby("edr_chave"):
        pior = grupo.sort_values("t2m_min").iloc[0]
        data_evento = pd.Timestamp(pior["data_inicio"])
        if (hoje - data_evento.date()).days < 17:
            pulados.append((chave, "aguardar ~2 semanas pós-evento p/ NDVI"))
            continue
        janela_fim = min(45, (hoje - data_evento.date()).days - 2)
        print(f"\nmedindo ΔNDVI em {chave} (evento {data_evento.date()}, até +{janela_fim}d)...")
        resultado = dano.dano_geada_edr(
            chave, data_evento.date().isoformat(), celulas,
            janela_depois=(7, janela_fim),
        )
        resultado["t2m_min"] = float(pior["t2m_min"])
        resultados.append(resultado)

    for chave, motivo in pulados:
        print(f"[adiado] {chave}: {motivo}")
    if not resultados:
        return 0

    producao = iea.cafe_edr(config.PASTA_IEA)
    ano_base = int(producao["ano"].max())
    base = producao[producao["ano"] == ano_base][["edr_chave", "producao_sc60"]]
    precos = iea.preco_recebido(config.PASTA_IEA_RECEBIDOS)
    serie = precos[(precos["produto"] == "Café benef. secagem natural") & (precos["moeda"] == "R$")]
    preco = float(serie.sort_values("data")["preco"].iloc[-1])

    clima_minimos = (
        alvo.groupby("edr_chave", as_index=False)["t2m_min"].min()
    )
    tabela = perda.tabela_evento(resultados, base, preco, clima_minimos)
    print(f"\n=== perda estimada (base IEA {ano_base}; preço R$ {preco:,.2f}/sc) ===")
    print(tabela.to_string(index=False))

    pasta = config.PASTA_PROCESSADOS / "relatorios"
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"geada_{inicio}_{fim}.csv"
    tabela.to_csv(caminho, index=False)
    print(f"\nsalvo: {caminho}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    raise SystemExit(principal())
