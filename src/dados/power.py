"""Cliente da API NASA POWER — clima diário por ponto, sem autenticação.

Reanálise MERRA-2 (célula ~0,5° ≈ 50 km), cobertura 1981–presente.
Docs: https://power.larc.nasa.gov/docs/
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import requests

URL = "https://power.larc.nasa.gov/api/temporal/daily/point"

# Parâmetros agroclimáticos (comunidade AG)
PARAMETROS_PADRAO = (
    "T2M",                # temperatura média a 2 m [°C]
    "T2M_MAX",            # máxima diária [°C]
    "T2M_MIN",            # mínima diária [°C] — geadas!
    "PRECTOTCORR",        # precipitação corrigida [mm/dia]
    "RH2M",               # umidade relativa [%]
    "ALLSKY_SFC_SW_DWN",  # radiação solar incidente
)


def clima_diario(
    lat: float,
    lon: float,
    inicio,
    fim,
    parametros: tuple[str, ...] = PARAMETROS_PADRAO,
) -> pd.DataFrame:
    """Série diária de clima para um ponto; datas "AAAA-MM-DD", "AAAAMMDD" ou date."""
    resposta = requests.get(
        URL,
        params={
            "parameters": ",".join(parametros),
            "community": "AG",
            "latitude": lat,
            "longitude": lon,
            "start": _formatar(inicio),
            "end": _formatar(fim),
            "format": "JSON",
        },
        timeout=180,
    )
    resposta.raise_for_status()
    dados = resposta.json()["properties"]["parameter"]
    df = pd.DataFrame(dados)
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df.index.name = "data"
    return df.replace(-999.0, np.nan)


def _formatar(data) -> str:
    if hasattr(data, "strftime"):
        return data.strftime("%Y%m%d")
    return str(data).replace("-", "")
