"""Utilidades compartilhadas dos módulos de dados."""
from __future__ import annotations

import unicodedata


def chave_regiao(nome: str) -> str:
    """Chave de junção normalizada para nomes de região (EDR, RA, município).

    Remove acentos, troca hífen por espaço, caixa alta e colapsa espaços —
    faz "Guaratinguetá", "GUARATINGUETA" e "Mogi-Mirim"/"MOGI MIRIM" casarem.
    """
    s = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode()
    s = s.upper().replace("-", " ")
    return " ".join(s.split())
