"""Cliente da API SIDRA (IBGE) — Produção Agrícola Municipal (PAM).

Tabela 1613: lavouras permanentes (inclui café), por município, 1974–2024.
Sem autenticação. Docs: https://apisidra.ibge.gov.br/

Ids verificados nos metadados em 12/08/2026:
  v112 Rendimento médio da produção [kg/ha]
  v214 Quantidade produzida [t]
  v216 Área colhida [ha]
  c82  Produto: 2723 = Café (em grão) Total
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping

import pandas as pd
import requests

URL_BASE = "https://apisidra.ibge.gov.br/values"
TABELA_LAVOURAS_PERMANENTES = "1613"

VAR_RENDIMENTO = "112"
VAR_PRODUCAO = "214"
VAR_AREA_COLHIDA = "216"

# Colunas da resposta: D1=município, D2=variável, D3=ano, D4=produto, V=valor
_RENOMEAR = {
    "D1C": "municipio_codigo",
    "D1N": "municipio",
    "D2N": "variavel",
    "D3N": "ano",
    "D4N": "produto",
    "V": "valor",
}


def consultar(
    tabela: str,
    municipios: Iterable[str],
    variaveis: Iterable[str],
    periodos: str,
    classificacoes: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """Consulta genérica; retorna DataFrame tidy (município/ano/variável por linha).

    ``periodos`` aceita "2024", "2019-2024", "last" etc. (sintaxe do apisidra).
    """
    partes = [
        URL_BASE,
        "t", tabela,
        "n6", ",".join(municipios),
        "v", ",".join(variaveis),
        "p", periodos,
    ]
    if classificacoes:
        for chave, itens in classificacoes.items():
            partes += [chave, itens]
    url = "/".join(partes) + "?formato=json"
    resposta = requests.get(url, timeout=120)
    resposta.raise_for_status()
    linhas = resposta.json()
    if not isinstance(linhas, list) or len(linhas) < 2:
        raise RuntimeError(f"Resposta inesperada do SIDRA para {url}")
    df = pd.DataFrame(linhas[1:])  # linha 0 é o cabeçalho
    df = df.rename(columns=_RENOMEAR)
    df = df[[c for c in _RENOMEAR.values() if c in df.columns]]
    # "..." (não existe) e "-" (zero por arredondamento) viram NaN
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    df["ano"] = df["ano"].astype(int)
    return df


def cafe_municipal(
    municipios: Iterable[str],
    periodos: str = "1990-2024",
    produto: str = "2723",
) -> pd.DataFrame:
    """Rendimento (kg/ha), produção (t) e área colhida (ha) de café por município/ano.

    Retorna DataFrame largo com colunas:
    municipio_codigo, municipio, ano, area_colhida_ha, producao_t, rendimento_kg_ha
    """
    tidy = consultar(
        TABELA_LAVOURAS_PERMANENTES,
        municipios,
        [VAR_RENDIMENTO, VAR_PRODUCAO, VAR_AREA_COLHIDA],
        periodos,
        {"c82": produto},
    )
    nomes = {
        "Rendimento médio da produção": "rendimento_kg_ha",
        "Quantidade produzida": "producao_t",
        "Área colhida": "area_colhida_ha",
    }
    tidy["variavel"] = tidy["variavel"].map(nomes).fillna(tidy["variavel"])
    largo = tidy.pivot_table(
        index=["municipio_codigo", "municipio", "ano"],
        columns="variavel",
        values="valor",
        aggfunc="first",
    ).reset_index()
    largo.columns.name = None
    return largo.sort_values(["municipio", "ano"]).reset_index(drop=True)
