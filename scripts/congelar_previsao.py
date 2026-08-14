"""Congela as previsões correntes no placar público (previsoes/).

Uso:
    .venv\\Scripts\\python scripts\\congelar_previsao.py            # todas as culturas
    .venv\\Scripts\\python scripts\\congelar_previsao.py --cultura cafe

Regra: um congelamento por cultura/ano/dia; registros nunca são editados.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import nowcast, placar


def principal() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cultura", default=None, choices=sorted(nowcast.CULTURAS))
    argumentos = parser.parse_args()
    culturas = [argumentos.cultura] if argumentos.cultura else sorted(nowcast.CULTURAS)

    for cultura in culturas:
        try:
            id_previsao = placar.congelar(cultura)
        except FileNotFoundError as erro:
            print(f"[{cultura}] pulado: {erro}")
            continue
        if id_previsao is None:
            print(f"[{cultura}] já congelada hoje — nada a fazer")
        else:
            print(f"[{cultura}] congelada: {id_previsao}")

    registro = placar.carregar_registro()
    print(f"\nregistro: {len(registro)} previsões congeladas em {placar.CAMINHO_REGISTRO}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    raise SystemExit(principal())
