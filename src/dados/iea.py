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


def valor_producao(caminho: str | Path) -> pd.DataFrame:
    """Valor da Produção (VPA) por produto/EDR/ano — aba "Dados" do export.

    Colunas: produto, grupo, edr, ano, calculo, preco, producao, unidade,
    valor, edr_chave. Preços e valores deflacionados pelo IPCA (o mês de
    referência está no cabeçalho do arquivo). Aceita arquivo, pasta ou lista.
    """
    quadros = []
    for arquivo in _resolver(caminho):
        df = pd.read_excel(arquivo, sheet_name="Dados", skiprows=6)
        df = df.dropna(subset=["Ano"]).rename(
            columns={
                "Produto": "produto",
                "Grupo": "grupo",
                "Região": "edr",
                "Ano": "ano",
                "Cálculo": "calculo",
                "Preço": "preco",
                "Produção": "producao",
                "Unidade": "unidade",
                "Valor da Produção": "valor",
            }
        )
        quadros.append(df)
    tidy = pd.concat(quadros, ignore_index=True)
    tidy["ano"] = tidy["ano"].astype(int)
    for coluna in ("preco", "producao", "valor"):
        tidy[coluna] = pd.to_numeric(tidy[coluna], errors="coerce")
    tidy["edr_chave"] = tidy["edr"].map(chave_regiao)
    return tidy.drop_duplicates(
        subset=["produto", "edr", "ano"], keep="last"
    ).reset_index(drop=True)


def preco_atacado(caminho: str | Path) -> pd.DataFrame:
    """Preços médios mensais de venda no atacado (município de São Paulo).

    Colunas: produto, ano, mes, data, moeda, preco, unidade. Série desde 1966;
    atenção à coluna ``moeda`` antes do Plano Real. Aceita arquivo/pasta/lista.
    """
    quadros = []
    for arquivo in _resolver(caminho):
        df = pd.read_excel(arquivo, skiprows=5)
        df = df.dropna(subset=["Ano"]).rename(
            columns={
                "Produto": "produto",
                "Mês": "mes",
                "Ano": "ano",
                "Moeda": "moeda",
                "Preço": "preco",
                "Unidade": "unidade",
            }
        )
        quadros.append(df)
    tidy = pd.concat(quadros, ignore_index=True)
    tidy["ano"] = tidy["ano"].astype(int)
    tidy["mes"] = tidy["mes"].astype(int)
    tidy["preco"] = pd.to_numeric(tidy["preco"], errors="coerce")
    tidy = tidy.drop_duplicates(subset=["produto", "ano", "mes"], keep="last")
    tidy["data"] = pd.to_datetime(
        {"year": tidy["ano"], "month": tidy["mes"], "day": 1}
    )
    colunas = ["produto", "ano", "mes", "data", "moeda", "preco", "unidade"]
    return tidy[colunas].sort_values(["produto", "data"]).reset_index(drop=True)


def _estatisticas_edr(caminho: str | Path, rotulo_produto: str) -> pd.DataFrame:
    """Parser comum dos levantamentos com estatísticas por EDR.

    Formato compartilhado por Salários Rurais e Pagamento de Colheita:
    Produto | Unidade | Região | Ano | Mês | Menor | Maior | Médio | Moda |
    Mediana | Nº de Informantes | Nº de Municípios.
    """
    quadros = []
    for arquivo in _resolver(caminho):
        df = pd.read_excel(arquivo, skiprows=5)
        df = df.dropna(subset=["Ano"]).rename(
            columns={
                "Produto": rotulo_produto,
                "Unidade": "unidade",
                "Região": "edr",
                "Ano": "ano",
                "Mês": "mes",
                "Menor": "menor",
                "Maior": "maior",
                "Médio": "medio",
                "Moda": "moda",
                "Mediana": "mediana",
                "Número de Informantes": "informantes",
                "Número de Municípios": "municipios",
            }
        )
        quadros.append(df)
    tidy = pd.concat(quadros, ignore_index=True)
    tidy[rotulo_produto] = tidy[rotulo_produto].str.strip()
    tidy["ano"] = tidy["ano"].astype(int)
    tidy["mes"] = tidy["mes"].astype(int)
    for coluna in ("menor", "maior", "medio", "moda", "mediana"):
        tidy[coluna] = pd.to_numeric(tidy[coluna], errors="coerce")
    tidy = tidy.drop_duplicates(subset=[rotulo_produto, "edr", "ano", "mes"], keep="last")
    tidy["data"] = pd.to_datetime({"year": tidy["ano"], "month": tidy["mes"], "day": 1})
    tidy["edr_chave"] = tidy["edr"].map(chave_regiao)
    colunas = [
        rotulo_produto, "unidade", "edr", "edr_chave", "ano", "mes", "data",
        "menor", "maior", "medio", "moda", "mediana", "informantes", "municipios",
    ]
    return tidy[[c for c in colunas if c in tidy.columns]].sort_values(
        [rotulo_produto, "edr", "data"]
    ).reset_index(drop=True)


def salarios_rurais(caminho: str | Path) -> pd.DataFrame:
    """Salários rurais por categoria/EDR (levantamentos de abril e novembro).

    Categorias: Administrador, Capataz, Diarista a seco, Mensalista,
    Tratorista, Volante. Série desde 1992, em R$. Aceita arquivo/pasta/lista.
    """
    return _estatisticas_edr(caminho, "categoria")


def pagamento_colheita(caminho: str | Path) -> pd.DataFrame:
    """Preço pago pela colheita por cultura/EDR (abril e junho, desde 1996).

    Culturas incluem Café Cereja e Café Coco (R$/sc de 100–110 litros),
    algodão (R$/@), cana (R$/t), citros (R$/cx.) etc. A coluna ``cultura``
    vem sem o prefixo "Preço médio pago pela Colheita de".
    """
    tidy = _estatisticas_edr(caminho, "cultura")
    tidy["cultura"] = (
        tidy["cultura"]
        .str.replace(r"^Preço médio pago pela Colheita de\s*", "", regex=True)
        .str.strip()
    )
    return tidy


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
