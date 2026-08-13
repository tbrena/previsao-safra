"""Painel do projeto Previsão de Safra — café paulista.

Uso:
    .venv\\Scripts\\streamlit run app\\painel.py

Lê as saídas pré-computadas de ``data/processed/`` (gere com
``scripts/rodar_nowcast.py``) e as séries do IEA em ``data/raw/iea/``.
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import config
from src.dados import geo, iea

# ---------------------------------------------------------------- tokens
COR = {
    "s1": "#2a78d6",  # série 1 (azul)
    "s2": "#eb6834",  # série 2 (laranja)
    "s3": "#1baf7a",  # série 3 (aqua)
    "tinta": "#0b0b0b",
    "tinta2": "#52514e",
    "mudo": "#898781",
    "grade": "#e1e0d9",
    "eixo": "#c3c2b7",
    "superficie": "#fcfcfb",
}
RAMPA_AZUL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

MODELO_LAYOUT = dict(
    paper_bgcolor=COR["superficie"],
    plot_bgcolor=COR["superficie"],
    font=dict(family='system-ui, "Segoe UI", sans-serif', color=COR["tinta"], size=13),
    margin=dict(l=10, r=10, t=40, b=10),
    xaxis=dict(gridcolor=COR["grade"], linecolor=COR["eixo"], zerolinecolor=COR["grade"]),
    yaxis=dict(gridcolor=COR["grade"], linecolor=COR["eixo"], zerolinecolor=COR["grade"]),
    hoverlabel=dict(bgcolor="#ffffff", font_color=COR["tinta"]),
)


# ---------------------------------------------------------------- dados
@st.cache_data(show_spinner=False)
def carregar_processados():
    pasta = config.PASTA_PROCESSADOS
    saida = {}
    for nome in ("previsao", "metricas", "loyo", "importancias", "dataset"):
        caminho = pasta / f"nowcast_{nome}.csv"
        saida[nome] = pd.read_csv(caminho) if caminho.exists() else None
    return saida


@st.cache_data(show_spinner=False)
def carregar_series_iea():
    cafe = iea.cafe_edr(config.PASTA_IEA)
    precos = iea.preco_recebido(config.PASTA_IEA_RECEBIDOS)
    preco_cafe = precos[
        (precos["produto"] == "Café benef. secagem natural") & (precos["moeda"] == "R$")
    ][["data", "preco"]]
    return cafe, preco_cafe


@st.cache_resource(show_spinner=False)
def carregar_geojson():
    edrs = geo.carregar_edrs(config.CAMINHO_EDRS)
    edrs = edrs.set_geometry(edrs.geometry.simplify(0.005))
    return edrs.__geo_interface__


# ---------------------------------------------------------------- página
st.set_page_config(page_title="Previsão de Safra — Café SP", page_icon="☕", layout="wide")
st.title("☕ Previsão de Safra — Café Paulista")
st.caption(
    "Satélite gratuito (Sentinel-2, MapBiomas) + clima (NASA POWER) + IEA/CATI + IBGE. "
    "Nível: CATI Regional/EDR."
)

dados = carregar_processados()
cafe, preco_cafe = carregar_series_iea()

aba_previsao, aba_entenda, aba_series, aba_geada, aba_metodo = st.tabs(
    ["📈 Previsão da safra", "🧭 Entenda o sistema", "🗺️ Séries por EDR",
     "❄️ Monitor de geada", "📚 Metodologia"]
)

# ---------------------------------------------------------------- aba 1
with aba_previsao:
    previsao = dados["previsao"]
    metricas = dados["metricas"]
    if previsao is None:
        st.warning("Rode `scripts/rodar_nowcast.py` para gerar a previsão.")
    else:
        ano_prev = int(previsao["ano"].iloc[0])
        ultimo_ano = int(cafe["ano"].max())
        cobertos = set(previsao["edr_chave"])
        base_ant = cafe[(cafe["ano"] == ultimo_ano) & (cafe["edr_chave"].isin(cobertos))]

        producao_prev = previsao["producao_prevista_sc60"].sum()
        producao_ant = base_ant["producao_sc60"].sum()
        rend_prev = 60.0 * producao_prev / previsao["area_ha"].sum()
        rend_ant = 60.0 * producao_ant / base_ant["area_producao_ha"].sum()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric(
            f"Produção prevista {ano_prev}",
            f"{producao_prev / 1e6:.2f} M sc",
            f"{100 * (producao_prev / producao_ant - 1):+.1f}% vs {ultimo_ano}",
        )
        c2.metric(f"Rendimento médio {ano_prev}", f"{rend_prev:,.0f} kg/ha",
                  f"{100 * (rend_prev / rend_ant - 1):+.1f}% vs {ultimo_ano}")
        if metricas is not None:
            linha = metricas.iloc[0]
            c3.metric("Erro do modelo (validação)", f"{linha['mae_modelo']:,.0f} kg/ha",
                      f"{100 * (1 - linha['mae_modelo'] / linha['mae_persistencia']):.0f}% melhor que persistência",
                      delta_color="off")
            c4.metric("Observações de treino", f"{int(linha['n_observacoes'])}",
                      str(linha["anos"]), delta_color="off")
        st.caption(
            f"Cobertura: {len(previsao)} EDRs (~"
            f"{100 * producao_ant / cafe[cafe['ano'] == ultimo_ano]['producao_sc60'].sum():.0f}% "
            f"da produção estadual de {ultimo_ano}). Faixas = ±MAE do EDR na validação."
        )

        col_mapa, col_barras = st.columns([1, 1])
        with col_mapa:
            fig = go.Figure(
                go.Choropleth(
                    geojson=carregar_geojson(),
                    featureidkey="properties.edr_chave",
                    locations=previsao["edr_chave"],
                    z=previsao["previsto_kg_ha"],
                    colorscale=[[i / (len(RAMPA_AZUL) - 1), c] for i, c in enumerate(RAMPA_AZUL)],
                    marker_line_color="#ffffff",
                    marker_line_width=1.0,
                    colorbar=dict(title="kg/ha", thickness=12, outlinewidth=0),
                    hovertemplate="<b>%{location}</b><br>previsto: %{z:,.0f} kg/ha<extra></extra>",
                )
            )
            fig.update_geos(fitbounds="locations", visible=False)
            fig.update_layout(**MODELO_LAYOUT, title=f"Rendimento previsto {ano_prev} (kg/ha)", height=430)
            st.plotly_chart(fig, use_container_width=True)

        with col_barras:
            ordenado = previsao.sort_values("producao_prevista_sc60", ascending=True).tail(10)
            reais = base_ant.set_index("edr_chave")["producao_sc60"].reindex(ordenado["edr_chave"])
            fig = go.Figure()
            fig.add_bar(
                y=ordenado["edr"], x=reais / 1000, name=f"{ultimo_ano} (IEA)",
                orientation="h", marker_color=COR["s1"],
                hovertemplate="<b>%{y}</b> %{x:,.0f} mil sc<extra></extra>",
            )
            fig.add_bar(
                y=ordenado["edr"], x=ordenado["producao_prevista_sc60"] / 1000,
                name=f"{ano_prev} (modelo)", orientation="h", marker_color=COR["s2"],
                hovertemplate="<b>%{y}</b> %{x:,.0f} mil sc<extra></extra>",
            )
            fig.update_layout(
                **MODELO_LAYOUT, barmode="group", bargap=0.25,
                title="Produção por EDR (mil sacas) — top 10",
                legend=dict(orientation="h", y=1.08), height=430,
            )
            st.plotly_chart(fig, use_container_width=True)

        st.subheader("Tabela por EDR")
        tabela = previsao[
            ["edr", "rendimento_a1", "previsto_kg_ha", "mae_kg_ha", "area_ha",
             "producao_prevista_sc60", "anom_florada_pct", "tmin_inverno_anterior"]
        ].rename(columns={
            "edr": "EDR", "rendimento_a1": f"rend. {ano_prev - 1} (kg/ha)",
            "previsto_kg_ha": f"previsto {ano_prev} (kg/ha)", "mae_kg_ha": "±MAE",
            "area_ha": "área (ha)", "producao_prevista_sc60": "produção prevista (sc)",
            "anom_florada_pct": "anomalia florada (%)", "tmin_inverno_anterior": "T mín. inverno ant. (°C)",
        })
        st.dataframe(tabela, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------- aba entenda
with aba_entenda:
    st.subheader("O que este sistema faz")
    st.markdown(
        """
Duas coisas, em linguagem direta:

1. **Prevê a colheita de café de São Paulo, região por região, meses antes da colheita** — com margem de erro declarada.
2. **Quando vem geada, mede o estrago em cerca de duas semanas** — meses antes dos levantamentos oficiais de campo.

Tudo com dados **públicos e gratuitos**: satélite, clima e as estatísticas oficiais do IEA/CATI.
"""
    )

    st.subheader("A ideia em um minuto ☕")
    st.markdown(
        """
O cafeeiro é como um atleta que alterna **ano de esforço e ano de descanso** — carrega
muito numa safra, descansa na seguinte (é a *bienalidade*). Então, para estimar a
próxima colheita, o sistema pergunta o que um bom agrônomo perguntaria:

| Pergunta | Onde o sistema busca a resposta |
|---|---|
| Em que fase do ciclo essa região está? | Histórico oficial de 16 anos (IEA) |
| Choveu bem na **florada** (set–nov), quando a planta define quantos frutos terá? | Clima diário da NASA, região por região |
| O inverno passado teve **geada** que machucou as plantas? | Termômetro (NASA) + fotos de satélite |
| Quanta lavoura existe de pé? | Levantamento de área do IEA |
| O preço está animando o produtor a investir no trato? | Série de preços do IEA (desde 1948) |

O modelo aprende, nos 16 anos de histórico, **como essas respostas se combinavam com a
colheita que de fato aconteceu** — e aplica o padrão ao ano atual.
"""
    )

    st.subheader('Como sabemos que funciona? A "prova dos anos escondidos"')
    st.markdown(
        """
Não avaliamos o modelo no dado que ele decorou — fazemos uma prova de verdade:

> **Escondemos um ano inteiro** (digamos, 2015). O modelo treina com todos os outros
> anos e tem que "adivinhar" 2015 sem nunca tê-lo visto. Corrigimos a prova e anotamos
> o erro. **Repetimos isso para cada um dos 14 anos.**

Resultado: **196 previsões às cegas**, com erro médio de **~3 sacas por hectare**
(o rendimento típico é de ~24 sc/ha — erro na casa de 12%). E o modelo erra **menos
que os dois chutes honestos** possíveis: "repetir o ano passado" e "repetir o último
ano de mesma fase do ciclo". Se fosse só sorte, ele não venceria os dois, catorze anos seguidos.
"""
    )

    st.subheader("E a geada? O caminho do alerta ao prejuízo ❄️")
    st.markdown(
        """
1. **No dia**: o termômetro (dados NASA) acusa madrugada perigosa numa região cafeeira.
2. **Duas semanas depois**: comparamos as fotos de satélite de **antes e depois**, só
   nos pixels onde há café (mapa MapBiomas), e medimos quanto do verde queimou —
   descontando o amarelado normal do inverno, medido nas áreas vizinhas sem café.
3. **A conta**: % da lavoura danificada → sacas perdidas → **reais**, usando o preço
   que o produtor recebe.

Esse método foi testado na **geada histórica de julho/2021**: onde fez mais frio, o
satélite viu mais dano (Ourinhos e Avaré, as mais frias, tiveram 3–4× mais área
queimada que o normal); onde não gelou, não viu quase nada; e num ano **sem** geada
(2019), o teste não acusou dano nenhum — ou seja, ele não "inventa" catástrofe.
"""
    )

    st.subheader("O que o sistema NÃO faz (tão importante quanto)")
    st.markdown(
        """
- **Não substitui o levantamento oficial** — antecipa e complementa; a palavra final é do IEA/CONAB/IBGE.
- **Não enxerga talhão individual** — o recorte é regional (EDR); fazenda a fazenda exigiria outro desenho.
- **Não prevê preço** — usa o preço como contexto, prever mercado é outro problema.
- **Não acerta na mosca** — entrega número **com margem** (~3 sc/ha). Quem promete precisão absoluta em agricultura não está sendo honesto.
"""
    )

    st.subheader("Mini-glossário")
    st.markdown(
        """
| Termo | Tradução |
|---|---|
| **EDR** | "Região rural" oficial da CATI — SP tem 40 (Franca, Avaré, Marília…) |
| **Saca** | 60 kg de café beneficiado — a unidade do mercado |
| **kg/ha** | Quilos colhidos por hectare de lavoura — a produtividade |
| **Bienalidade** | O "ano sim, ano não" natural do cafeeiro |
| **Florada** | Set–nov: quando a chuva define quantos frutos a planta terá |
| **NDVI** | Nota de "quão verde e vigorosa" está a vegetação, vista do espaço |
| **Margem de erro (MAE)** | O quanto o modelo costuma errar, medido na prova dos anos escondidos |
"""
    )

# ---------------------------------------------------------------- aba 2
with aba_series:
    nomes = cafe.sort_values("edr")["edr"].unique().tolist()
    grandes = cafe.groupby("edr")["producao_sc60"].mean().sort_values(ascending=False)
    escolhido = st.selectbox("EDR", nomes, index=nomes.index(grandes.index[0]))
    serie = cafe[cafe["edr"] == escolhido].sort_values("ano")
    chave = serie["edr_chave"].iloc[0]

    col_a, col_b = st.columns([2, 1])
    with col_a:
        fig = go.Figure()
        fig.add_scatter(
            x=serie["ano"], y=serie["rendimento_kg_ha"], mode="lines+markers",
            name="rendimento (IEA)", line=dict(color=COR["s1"], width=2),
            marker=dict(size=8),
            hovertemplate="%{x}: %{y:,.0f} kg/ha<extra></extra>",
        )
        previsao = dados["previsao"]
        if previsao is not None and chave in set(previsao["edr_chave"]):
            linha = previsao[previsao["edr_chave"] == chave].iloc[0]
            fig.add_scatter(
                x=[int(linha["ano"])], y=[linha["previsto_kg_ha"]],
                mode="markers+text", name="previsto (modelo)",
                marker=dict(color=COR["s2"], size=12, symbol="diamond"),
                text=[f"{linha['previsto_kg_ha']:,.0f}"], textposition="top center",
                textfont=dict(color=COR["tinta2"]),
                error_y=dict(type="data", array=[linha["mae_kg_ha"]], color=COR["s2"], thickness=2),
                hovertemplate="previsto %{x}: %{y:,.0f} kg/ha<extra></extra>",
            )
        fig.update_layout(
            **MODELO_LAYOUT, title=f"Rendimento — {escolhido} (kg/ha)",
            legend=dict(orientation="h", y=1.1), height=380,
        )
        st.plotly_chart(fig, use_container_width=True)
    with col_b:
        fig = go.Figure(
            go.Bar(
                x=serie["ano"], y=serie["area_producao_ha"] / 1000,
                marker_color=COR["s1"],
                hovertemplate="%{x}: %{y:,.1f} mil ha<extra></extra>",
            )
        )
        fig.update_layout(**MODELO_LAYOUT, title="Área em produção (mil ha)", height=380, bargap=0.3)
        st.plotly_chart(fig, use_container_width=True)

    fig = go.Figure(
        go.Scatter(
            x=preco_cafe["data"], y=preco_cafe["preco"], mode="lines",
            line=dict(color=COR["s1"], width=2),
            hovertemplate="%{x|%m/%Y}: R$ %{y:,.0f}/sc<extra></extra>",
        )
    )
    fig.update_layout(
        **MODELO_LAYOUT, height=300,
        title="Preço recebido pelo produtor — café secagem natural (R$/sc 60 kg, nominal, estado de SP)",
    )
    st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------- aba 3
with aba_geada:
    st.subheader("Situação do inverno atual")
    st.write(
        "Varredura diária de risco por T2M_MIN (NASA POWER) nos 13 EDRs cafeeiros. "
        "Rode `scripts/avaliar_geada.py` para atualizar; com severidade ≥ moderada o "
        "pipeline mede o dano por ΔNDVI (Sentinel-2) sobre as células de café."
    )
    relatorios = sorted((config.PASTA_PROCESSADOS / "relatorios").glob("geada_*.csv"))
    if relatorios:
        ultimo = relatorios[-1]
        st.success(f"✅ Última avaliação com dano medido: `{ultimo.name}`")
        st.dataframe(pd.read_csv(ultimo), use_container_width=True, hide_index=True)
    else:
        st.info("✅ Inverno de 2026 até 10/08: nenhum evento acima da faixa 'atenção' (mín. 5,9 °C em SJBV, 14/07). Sem medição NDVI necessária.")

    st.subheader("Backtest — geada de julho/2021")
    st.write(
        "Validação do método: dose-resposta térmica confirmada (dano NDVI cresce onde "
        "fez mais frio; placebo 2019 limpo). Perda direta visível por satélite:"
    )
    backtest = pd.DataFrame({
        "EDR": ["São João da Boa Vista", "Franca", "Ourinhos", "Avaré", "Marília"],
        "T2M mín (°C)": [2.0, 4.5, 1.8, 0.9, 3.3],
        "área c/ queda forte (%)": [7.2, 3.7, 11.0, 10.2, 2.7],
        "perda estimada (%)": [6.9, 1.4, 9.2, 7.2, 0.3],
        "sacas perdidas": [94537, 39726, 33178, 11038, 1680],
        "R$ (preço 2022)": ["119,9 mi", "50,4 mi", "42,1 mi", "14,0 mi", "2,1 mi"],
    })
    st.dataframe(backtest, use_container_width=True, hide_index=True)
    st.caption(
        "Total: ~180 mil sc [89–269 mil] ≈ R$ 228 mi — ~10% da quebra total de SP "
        "2020→2022; o restante veio de seca 2020-21, poda pós-geada e bienalidade "
        "(ver relatorios/backtest_geada_jul2021.md)."
    )

# ---------------------------------------------------------------- aba 4
with aba_metodo:
    st.markdown(
        """
### Fontes (todas gratuitas)
| Fonte | Papel |
|---|---|
| **IEA/CATI — SAAESP** | produção/área por EDR 2010–2025 (alvo do modelo), preços recebidos desde 1948, salários e pagamento de colheita |
| **NASA POWER (MERRA-2)** | clima diário por EDR desde 2009 |
| **Sentinel-2 (STAC/AWS)** | ΔNDVI de eventos sobre as áreas de café |
| **MapBiomas Coleção 9** | onde está o café (classe 46, 30 m) |
| **IBGE PAM/SIDRA** | verdade municipal independente (QA) |

### Modelo (Sistema 2 — nowcast)
Random Forest por EDR × ano com features **conhecidas até o meio do ano da colheita**:
clima por janela fenológica (florada set–nov, enchimento dez–mar, geada do inverno
anterior), bienalidade (2 defasagens), área em produção e incentivo de preço.
**Validação leave-one-year-out**: o modelo nunca vê o ano que prevê; erro comparado
com persistência e média bienal. Faixas de incerteza = MAE por EDR da validação.

### Sistema 1 — resposta rápida a eventos
Detecção de geada no dia (limiar 6 °C na célula ~50 km ≈ 0 °C na relva, calibrado
em 2021) → ΔNDVI antes/depois restrito ao café, com o não-café como controle da
senescência → classes agronômicas → sacas e R$. Validado por dose-resposta e placebo.

### Limitações honestas
- Recorte municipal do IEA é apoio (o próprio IEA o considera menos confiável); a série oficial é por EDR.
- MapBiomas enxerga ~60% da área de café declarada (30 m perde café novo/sombreado/fragmentado) — usado para *localizar*, não para *quantificar*.
- A perda pós-geada em sacas usa classes agronômicas com faixa ±50%; a atribuição fina exige o nowcast com covariáveis (seca, poda, bienalidade).
- Clima em célula de ~50 km suaviza extremos locais (vales frios).

*Código: [github.com/tbrena/previsao-safra](https://github.com/tbrena/previsao-safra) (privado).*
"""
    )
