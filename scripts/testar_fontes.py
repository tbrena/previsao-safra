"""Teste de fumaça das três fontes de dados públicas do projeto.

Uso:
    .venv\\Scripts\\python scripts\\testar_fontes.py
"""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config
from src.dados import iea, power, satelite, sidra


def testar_sidra():
    df = sidra.cafe_municipal(["3170701", "3128709"], periodos="2019-2024")
    print(df.to_string(index=False))


def testar_power():
    lat, lon = config.COORDENADAS["3170701"]  # Varginha
    df = power.clima_diario(lat, lon, "2026-07-01", "2026-07-31")
    print(
        f"dias: {len(df)} | chuva total: {df['PRECTOTCORR'].sum():.1f} mm"
        f" | T2M média: {df['T2M'].mean():.1f} °C"
        f" | T2M mínima: {df['T2M_MIN'].min():.1f} °C"
    )


def testar_sentinel2():
    serie = satelite.serie_ndvi(config.AOI_GUAXUPE, "2026-07-01", "2026-08-12", max_nuvens=10)
    print(serie.to_string(index=False))


def testar_iea():
    if not config.PASTA_IEA.exists() or not any(config.PASTA_IEA.glob("*.xlsx")):
        print(f"[PULADO] nenhum export em: {config.PASTA_IEA}")
        return
    cafe = iea.cafe_edr(config.PASTA_IEA)
    print(f"EDRs: {cafe['edr'].nunique()} | anos: {cafe['ano'].min()}–{cafe['ano'].max()}")
    sp = cafe.groupby("ano")[["area_producao_ha", "producao_sc60"]].sum()
    sp["rendimento_kg_ha"] = (sp["producao_sc60"] * 60 / sp["area_producao_ha"]).round(0)
    print("Estado de SP (soma dos EDRs):")
    print(sp.to_string())


def principal():
    ok = True
    testes = [
        ("IBGE SIDRA — rendimento de café (PAM t1613)", testar_sidra),
        ("NASA POWER — clima diário", testar_power),
        ("Sentinel-2 via STAC — NDVI Guaxupé/MG", testar_sentinel2),
        ("IEA/CATI — café por EDR (arquivo local)", testar_iea),
    ]
    for nome, funcao in testes:
        print(f"\n=== {nome} ===")
        try:
            funcao()
            print("[OK]")
        except Exception:
            traceback.print_exc()
            print("[FALHOU]")
            ok = False
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    principal()
