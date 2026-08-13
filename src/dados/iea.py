"""Leitura das Estatísticas da Produção Paulista (IEA/CATI — SAAESP).

Planilhas exportadas do banco do IEA (Instituto de Economia Agrícola/SP),
agregação "CATI Regional / EDR". Layout do arquivo:

- 5 linhas de cabeçalho institucional (instituto, levantamento, região, período)
- linha 6: Produto | Região | Ano | Desc.C1 | C1 | Unid.C1 | ... até C3
- rodapé com fonte ("IEA/CATI - SAAESP"), data da pesquisa e copyright

Cada produto usa até 3 características (ex.: café = ÁREA NOVA, AREA EM
PRODUCAO, PRODUÇÃO). Unidades variam por produto (sc.60kg, @, t, cabeças...).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .util import chave_regiao

PRODUTO_CAFE = "Café (beneficiado)"
KG_POR_SACA = 60.0


def carregar(caminho: str | Path) -> pd.DataFrame:
    """Um ou mais exports em formato tidy.

    ``caminho`` pode ser um .xlsx, uma pasta (lê todos os .xlsx dela) ou uma
    lista de arquivos. Períodos sobrepostos são deduplicados (vence o arquivo
    lido por último, em ordem alfabética de nome).

    Colunas: produto, edr, ano, caracteristica, valor, unidade — uma linha por
    característica preenchida. Rodapé e linhas sem ano são descartados.
    """
    tidy = pd.concat([_carregar_um(c) for c in _resolver(caminho)], ignore_index=True)
    return tidy.drop_duplicates(
        subset=["produto", "edr", "ano", "caracteristica"], keep="last"
    ).reset_index(drop=True)


def _resolver(caminho) -> list[Path]:
    if isinstance(caminho, (list, tuple)):
        return [Path(c) for c in caminho]
    caminho = Path(caminho)
    if caminho.is_dir():
        arquivos = sorted(caminho.glob("*.xlsx"))
        if not arquivos:
            raise FileNotFoundError(f"Nenhum .xlsx em {caminho}")
        return arquivos
    return [caminho]


def _carregar_um(caminho: Path) -> pd.DataFrame:
    bruto = pd.read_excel(caminho, skiprows=5)
    bruto = bruto.dropna(subset=["Ano"])
    partes = []
    for n in (1, 2, 3):
        sub = bruto[["Produto", "Região", "Ano", f"Desc.C{n}", f"C{n}", f"Unid.C{n}"]].copy()
        sub.columns = ["produto", "edr", "ano", "caracteristica", "valor", "unidade"]
        partes.append(sub.dropna(subset=["caracteristica"]))
    tidy = pd.concat(partes, ignore_index=True)
    tidy["ano"] = tidy["ano"].astype(int)
    tidy["valor"] = pd.to_numeric(tidy["valor"], errors="coerce")
    return tidy


def cafe_edr(caminho: str | Path) -> pd.DataFrame:
    """Café beneficiado por EDR/ano.

    Colunas: edr, ano, area_nova_ha, area_producao_ha, producao_sc60 e
    rendimento_kg_ha (produção × 60 kg / área em produção — comparável ao
    rendimento do IBGE PAM, que também é café beneficiado).
    """
    tidy = carregar(caminho)
    cafe = tidy[tidy["produto"] == PRODUTO_CAFE]
    largo = cafe.pivot_table(
        index=["edr", "ano"], columns="caracteristica", values="valor", aggfunc="first"
    ).reset_index()
    largo.columns.name = None
    largo = largo.rename(
        columns={
            "ÁREA NOVA": "area_nova_ha",
            "AREA EM PRODUCAO": "area_producao_ha",
            "PRODUÇÃO": "producao_sc60",
        }
    )
    com_area = largo["area_producao_ha"] > 0
    largo["rendimento_kg_ha"] = (
        (largo["producao_sc60"] * KG_POR_SACA / largo["area_producao_ha"])
        .where(com_area)
        .round(0)
    )
    largo["edr_chave"] = largo["edr"].map(chave_regiao)
    return largo.sort_values(["edr", "ano"]).reset_index(drop=True)


def produto_edr(caminho: str | Path, produto: str) -> pd.DataFrame:
    """Qualquer produto em formato largo (característica → coluna)."""
    tidy = carregar(caminho)
    sel = tidy[tidy["produto"] == produto]
    if sel.empty:
        disponiveis = sorted(tidy["produto"].unique())
        raise ValueError(f"Produto {produto!r} não encontrado. Disponíveis: {disponiveis}")
    largo = sel.pivot_table(
        index=["edr", "ano"], columns="caracteristica", values="valor", aggfunc="first"
    ).reset_index()
    largo.columns.name = None
    largo["edr_chave"] = largo["edr"].map(chave_regiao)
    return largo.sort_values(["edr", "ano"]).reset_index(drop=True)
