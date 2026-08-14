"""Painel do projeto Previsão de Safra — culturas paulistas por EDR.

Uso:
    .venv\\Scripts\\streamlit run app\\painel.py

Lê as saídas pré-computadas de ``data/processed/`` (gere com
``scripts/rodar_nowcast.py --cultura ...``) e as séries do IEA.
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Purga módulos parcialmente importados de reruns anteriores (um import que
# falha no meio deixa o módulo pela metade no sys.modules — e o rerun seguinte
# quebraria com AttributeError em vez de mostrar o erro verdadeiro).
for _nome in [m for m in list(sys.modules) if m == "src" or m.startswith("src.")]:
    del sys.modules[_nome]
try:
    from src import config, nowcast
    from src.dados import geo, iea
except Exception:
    import traceback

    st.error("Falha ao carregar os módulos do projeto — detalhes abaixo:")
    st.code(traceback.format_exc())
    st.stop()

# ---------------------------------------------------------------- tokens
COR = {
    "s1": "#2a78d6",
    "s2": "#eb6834",
    "s3": "#1baf7a",
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

EMOJI = {"cafe": "☕", "laranja": "🍊", "amendoim": "🥜", "milho_safrinha": "🌽"}


# ---------------------------------------------------------------- dados
@st.cache_data(show_spinner=False)
def carregar_processados(cultura: str):
    pasta = config.PASTA_PROCESSADOS
    saida = {}
    for nome in ("previsao", "metricas", "loyo", "importancias"):
        caminho = pasta / f"nowcast_{cultura}_{nome}.csv"
        saida[nome] = pd.read_csv(caminho) if caminho.exists() else None
    return saida


@st.cache_data(show_spinner=False)
def carregar_serie_producao(cultura: str):
    cfg = nowcast.CULTURAS[cultura]
    return iea.producao_edr(config.PASTA_IEA, cfg["produtos"], cfg["kg_por_unidade"])


@st.cache_data(show_spinner=False)
def carregar_serie_preco(cultura: str):
    cfg = nowcast.CULTURAS[cultura]
    precos = iea.preco_recebido(config.PASTA_IEA_RECEBIDOS)
    sel = precos[(precos["produto"] == cfg["preco_produto"]) & (precos["moeda"] == "R$")]
    return sel[["data", "preco", "unidade"]]


@st.cache_resource(show_spinner=False)
def carregar_geojson():
    edrs = geo.carregar_edrs(config.CAMINHO_EDRS)
    edrs = edrs.set_geometry(edrs.geometry.simplify(0.005))
    return edrs.__geo_interface__


# ---------------------------------------------------------------- página
st.set_page_config(page_title="Previsão de Safra — SP", page_icon="🛰️", layout="wide")
st.title("🛰️ Previsão de Safra — Culturas Paulistas")
st.caption(
    "Satélite gratuito (Sentinel-2, MapBiomas) + clima (NASA POWER) + IEA/CATI + IBGE. "
    "Nível: CATI Regional/EDR."
)

rotulos = {chave: f"{EMOJI.get(chave, '')} {cfg['rotulo']}" for chave, cfg in nowcast.CULTURAS.items()}
cultura = st.radio(
    "Cultura", options=list(rotulos), format_func=rotulos.get, horizontal=True, label_visibility="collapsed"
)
cfg = nowcast.CULTURAS[cultura]

dados = carregar_processados(cultura)
serie_producao = carregar_serie_producao(cultura)
serie_preco = carregar_serie_preco(cultura)

aba_previsao, aba_entenda, aba_series, aba_geada, aba_metodo = st.tabs(
    ["📈 Previsão da safra", "🧭 Entenda o sistema", "🗺️ Séries por EDR",
     "❄️ Monitor de geada", "📚 Metodologia"]
)

# ---------------------------------------------------------------- aba 1
with aba_previsao:
    previsao = dados["previsao"]
    metricas = dados["metricas"]
    if previsao is None:
        st.warning(f"Rode `scripts/rodar_nowcast.py --cultura {cultura}` para gerar a previsão.")
    else:
        ano_prev = int(previsao["ano"].iloc[0])
        historico_alvo = serie_producao.dropna(subset=[cfg["alvo"]])
        ultimo_ano = int(historico_alvo["ano"].max())
        cobertos = set(previsao["edr_chave"])
        base_ant = historico_alvo[
            (historico_alvo["ano"] == ultimo_ano) & (historico_alvo["edr_chave"].isin(cobertos))
        ]

        producao_prev = previsao["producao_prevista_unid"].sum()
        producao_ant = base_ant["producao_unid"].sum()
        rend_prev = (
            previsao["producao_prevista_unid"].sum() * cfg["kg_por_unidade"] / previsao["capacidade"].sum()
            if cfg["alvo"] == "rendimento_kg_ha"
            else producao_prev / previsao["capacidade"].sum()
        )
        rend_ant = (
            base_ant["producao_unid"].sum() * cfg["kg_por_unidade"] / base_ant[cfg["capacidade"]].sum()
            if cfg["alvo"] == "rendimento_kg_ha"
            else producao_ant / base_ant[cfg["capacidade"]].sum()
        )

        c1, c2, c3, c4 = st.columns(4)
        c1.metric(
            f"Produção prevista {ano_prev}",
            f"{producao_prev / 1e6:.2f} M {cfg['unidade_producao']}",
            f"{100 * (producao_prev / producao_ant - 1):+.1f}% vs {ultimo_ano}",
        )
        c2.metric(
            f"Rendimento médio {ano_prev}",
            f"{rend_prev:,.2f} {cfg['unidade_alvo']}" if rend_prev < 50 else f"{rend_prev:,.0f} {cfg['unidade_alvo']}",
            f"{100 * (rend_prev / rend_ant - 1):+.1f}% vs {ultimo_ano}",
        )
        if metricas is not None:
            linha = metricas.iloc[0]
            c3.metric(
                "Erro do modelo (validação)",
                f"{linha['mae_modelo']:,.2f}" if linha["mae_modelo"] < 50 else f"{linha['mae_modelo']:,.0f}",
                f"{100 * (1 - linha['mae_modelo'] / linha['mae_persistencia']):.0f}% melhor que persistência",
                delta_color="off",
            )
            c4.metric("Observações de treino", f"{int(linha['n_observacoes'])}",
                      str(linha["anos"]), delta_color="off")
        st.caption(
            f"Cobertura: {len(previsao)} EDRs (~"
            f"{100 * producao_ant / historico_alvo[historico_alvo['ano'] == ultimo_ano]['producao_unid'].sum():.0f}% "
            f"da produção estadual de {ultimo_ano}). Faixas = ±MAE do EDR na validação."
        )

        col_mapa, col_barras = st.columns([1, 1])
        with col_mapa:
            fig = go.Figure(
                go.Choropleth(
                    geojson=carregar_geojson(),
                    featureidkey="properties.edr_chave",
                    locations=previsao["edr_chave"],
                    z=previsao["previsto"],
                    colorscale=[[i / (len(RAMPA_AZUL) - 1), c] for i, c in enumerate(RAMPA_AZUL)],
                    marker_line_color="#ffffff",
                    marker_line_width=1.0,
                    colorbar=dict(title=cfg["unidade_alvo"], thickness=12, outlinewidth=0),
                    hovertemplate="<b>%{location}</b><br>previsto: %{z:,.2f} "
                    + cfg["unidade_alvo"] + "<extra></extra>",
                )
            )
            fig.update_geos(fitbounds="locations", visible=False)
            fig.update_layout(
                **MODELO_LAYOUT,
                title=f"{cfg['rotulo']} — rendimento previsto {ano_prev} ({cfg['unidade_alvo']})",
                height=430,
            )
            st.plotly_chart(fig, use_container_width=True)

        with col_barras:
            ordenado = previsao.sort_values("producao_prevista_unid", ascending=True).tail(10)
            reais = (
                base_ant.set_index("edr_chave")["producao_unid"].reindex(ordenado["edr_chave"])
            )
            fig = go.Figure()
            fig.add_bar(
                y=ordenado["edr"], x=reais / 1000, name=f"{ultimo_ano} (IEA)",
                orientation="h", marker_color=COR["s1"],
                hovertemplate="<b>%{y}</b> %{x:,.0f} mil<extra></extra>",
            )
            fig.add_bar(
                y=ordenado["edr"], x=ordenado["producao_prevista_unid"] / 1000,
                name=f"{ano_prev} (modelo)", orientation="h", marker_color=COR["s2"],
                hovertemplate="<b>%{y}</b> %{x:,.0f} mil<extra></extra>",
            )
            fig.update_layout(
                **MODELO_LAYOUT, barmode="group", bargap=0.25,
                title=f"Produção por EDR (mil {cfg['unidade_producao']}) — top 10",
                legend=dict(orientation="h", y=1.08), height=430,
            )
            st.plotly_chart(fig, use_container_width=True)

        st.subheader("Tabela por EDR")
        tabela = previsao[
            ["edr", "rendimento_a1", "previsto", "mae", "capacidade",
             "producao_prevista_unid", "anom_critica_pct", "tmin_fria"]
        ].rename(columns={
            "edr": "EDR",
            "rendimento_a1": f"rend. {ano_prev - 1} ({cfg['unidade_alvo']})",
            "previsto": f"previsto {ano_prev} ({cfg['unidade_alvo']})",
            "mae": "±MAE",
            "capacidade": "área (ha)" if cfg["capacidade"] == "area_producao_ha" else "pés em produção",
            "producao_prevista_unid": f"produção prevista ({cfg['unidade_producao']})",
            "anom_critica_pct": "anomalia chuva janela crítica (%)",
            "tmin_fria": "T mín. janela fria (°C)",
        })
        st.dataframe(tabela, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------- aba entenda
with aba_entenda:
    st.subheader("O que este sistema faz")
    st.markdown(
        """
Duas coisas, em linguagem direta:

1. **Prevê a colheita por região (EDR), meses antes** — café, laranja, amendoim e
   milho safrinha — com margem de erro declarada.
2. **Quando vem geada, mede o estrago em cerca de duas semanas** (hoje no café;
   as demais culturas herdam o método).

Tudo com dados **públicos e gratuitos**: satélite, clima e as estatísticas oficiais do IEA/CATI.
"""
    )

    st.subheader("A ideia em um minuto")
    st.markdown(
        """
Culturas perenes (café, laranja) são como atletas que alternam **ano de esforço e
ano de descanso** — a *bienalidade*. Anuais (amendoim, milho safrinha) respondem
mais ao clima do próprio ciclo. Para estimar a colheita, o sistema pergunta o que
um bom agrônomo perguntaria:

| Pergunta | Onde o sistema busca a resposta |
|---|---|
| Em que fase do ciclo essa região está? | Histórico oficial do IEA (série desde 1983) |
| A lavoura está verde e vigorosa agora? | Fotos de satélite Sentinel-2 (desde 2017) |
| Choveu bem na **janela crítica** (florada/plantio)? | Clima diário da NASA, região por região |
| Teve **geada** no caminho? | Termômetro (NASA) + satélite |
| Quanta lavoura (ou quantos pés) existe? | Levantamento do IEA |
| O preço está animando o produtor? | Séries de preço do IEA (desde 1948) |

O modelo aprende, no histórico, **como essas respostas se combinavam com a colheita
que de fato aconteceu** — e aplica o padrão ao ano atual.
"""
    )

    st.subheader('Como sabemos que funciona? A "prova dos anos escondidos"')
    st.markdown(
        """
> **Escondemos um ano inteiro** (digamos, 2015). O modelo treina com todos os outros
> anos e tem que "adivinhar" 2015 sem nunca tê-lo visto. Corrigimos a prova e
> anotamos o erro. **Repetimos para cada ano da série.**

No café: 400 previsões às cegas (2001–2025), erro médio de ~3 sacas/ha. No regime
climático atual (2012+), o modelo erra **menos que os chutes honestos** ("repetir o
ano passado" e "repetir o último ano de mesma fase") — especialmente nas regiões
grandes, que definem a produção do estado. Cada cultura publica os próprios números
na aba Previsão — inclusive quando a validação ainda é limitada.
"""
    )

    st.subheader("O que o sistema NÃO faz")
    st.markdown(
        """
- **Não substitui o levantamento oficial** — antecipa e complementa.
- **Não enxerga talhão individual** — o recorte é regional (EDR).
- **Não prevê preço** — usa preço como contexto.
- **Não acerta na mosca** — entrega número **com margem**. Quem promete precisão
  absoluta em agricultura não está sendo honesto.
"""
    )

    st.subheader("Mini-glossário")
    st.markdown(
        """
| Termo | Tradução |
|---|---|
| **EDR** | "Região rural" oficial da CATI — SP tem 40 |
| **Saca / caixa** | Café e milho: sc 60 kg; amendoim: sc 25 kg; laranja: cx 40,8 kg |
| **cx/pé** | Rendimento da laranja: caixas por árvore (o IEA conta pés, não hectares) |
| **Bienalidade** | O "ano sim, ano não" natural das perenes |
| **Janela crítica** | Florada (café/laranja), plantio (amendoim), floração (milho) |
| **NDVI** | Nota de "quão verde e vigorosa" está a vegetação, vista do espaço |
| **MAE** | O quanto o modelo costuma errar, medido na prova dos anos escondidos |
"""
    )

# ---------------------------------------------------------------- aba séries
with aba_series:
    historico_alvo = serie_producao.dropna(subset=[cfg["alvo"]])
    nomes = historico_alvo.sort_values("edr")["edr"].unique().tolist()
    grandes = historico_alvo.groupby("edr")["producao_unid"].mean().sort_values(ascending=False)
    escolhido = st.selectbox("EDR", nomes, index=nomes.index(grandes.index[0]) if len(nomes) else 0)
    serie = historico_alvo[historico_alvo["edr"] == escolhido].sort_values("ano")
    chave = serie["edr_chave"].iloc[0]

    col_a, col_b = st.columns([2, 1])
    with col_a:
        fig = go.Figure()
        fig.add_scatter(
            x=serie["ano"], y=serie[cfg["alvo"]], mode="lines+markers",
            name="rendimento (IEA)", line=dict(color=COR["s1"], width=2),
            marker=dict(size=8),
            hovertemplate="%{x}: %{y:,.2f} " + cfg["unidade_alvo"] + "<extra></extra>",
        )
        previsao = dados["previsao"]
        if previsao is not None and chave in set(previsao["edr_chave"]):
            linha = previsao[previsao["edr_chave"] == chave].iloc[0]
            fig.add_scatter(
                x=[int(linha["ano"])], y=[linha["previsto"]],
                mode="markers", name="previsto (modelo)",
                marker=dict(color=COR["s2"], size=12, symbol="diamond"),
                error_y=dict(type="data", array=[linha["mae"]], color=COR["s2"], thickness=2),
                hovertemplate="previsto %{x}: %{y:,.2f} " + cfg["unidade_alvo"] + "<extra></extra>",
            )
        fig.update_layout(
            **MODELO_LAYOUT,
            title=f"{cfg['rotulo']} — rendimento em {escolhido} ({cfg['unidade_alvo']})",
            legend=dict(orientation="h", y=1.1), height=380,
        )
        st.plotly_chart(fig, use_container_width=True)
    with col_b:
        capacidade_rotulo = "mil ha" if cfg["capacidade"] == "area_producao_ha" else "milhões de pés"
        fator = 1000.0 if cfg["capacidade"] == "area_producao_ha" else 1e6
        fig = go.Figure(
            go.Bar(
                x=serie["ano"], y=serie[cfg["capacidade"]] / fator,
                marker_color=COR["s1"],
                hovertemplate="%{x}: %{y:,.1f} " + capacidade_rotulo + "<extra></extra>",
            )
        )
        fig.update_layout(
            **MODELO_LAYOUT,
            title=("Área em produção" if cfg["capacidade"] == "area_producao_ha" else "Pés em produção")
            + f" ({capacidade_rotulo})",
            height=380, bargap=0.3,
        )
        st.plotly_chart(fig, use_container_width=True)

    if not serie_preco.empty:
        unidade_preco = serie_preco["unidade"].iloc[-1]
        fig = go.Figure(
            go.Scatter(
                x=serie_preco["data"], y=serie_preco["preco"], mode="lines",
                line=dict(color=COR["s1"], width=2),
                hovertemplate="%{x|%m/%Y}: R$ %{y:,.2f}<extra></extra>",
            )
        )
        fig.update_layout(
            **MODELO_LAYOUT, height=300,
            title=f"Preço recebido pelo produtor — {cfg['preco_produto']} (R$/{unidade_preco}, nominal)",
        )
        st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------- aba geada
with aba_geada:
    st.subheader("Situação do inverno atual (café)")
    st.write(
        "Varredura diária de risco por T2M_MIN (NASA POWER) nos EDRs cafeeiros. "
        "Rode `scripts/avaliar_geada.py` para atualizar; com severidade ≥ moderada o "
        "pipeline mede o dano por ΔNDVI (Sentinel-2) sobre as células de café. "
        "Laranja e milho safrinha herdarão o mesmo método (máscaras já geradas para citros)."
    )
    relatorios = sorted((config.PASTA_PROCESSADOS / "relatorios").glob("geada_*.csv"))
    if relatorios:
        ultimo = relatorios[-1]
        st.success(f"✅ Última avaliação com dano medido: `{ultimo.name}`")
        st.dataframe(pd.read_csv(ultimo), use_container_width=True, hide_index=True)
    else:
        st.info("✅ Inverno de 2026 até 10/08: nenhum evento acima da faixa 'atenção' (mín. 5,9 °C em SJBV, 14/07). Sem medição NDVI necessária.")

    st.subheader("Backtest — geada de julho/2021 (café)")
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

# ---------------------------------------------------------------- aba metodologia
with aba_metodo:
    st.markdown(
        """
### Fontes (todas gratuitas)
| Fonte | Papel |
|---|---|
| **IEA/CATI — SAAESP** | produção por EDR desde 1983 (café em kg/ha desde 2001; laranja medida em **pés** desde sempre — por isso o alvo é cx/pé; amendoim = águas + seca somadas), preços desde 1948, salários e colheita |
| **NASA POWER (MERRA-2)** | clima diário por EDR desde 2000 |
| **Sentinel-2 (STAC/AWS)** | anomalia de NDVI nas janelas fenológicas (café e laranja, 2017+) e ΔNDVI de eventos |
| **MapBiomas Coleção 9** | onde estão as lavouras (classe 46 = café, 47 = citros) |
| **IBGE PAM/SIDRA** | verdade municipal independente (QA) |

### Modelo (Sistema 2 — nowcast, comum às culturas)
Gradient boosting (histogramas, aceita dados ausentes) por EDR × ano com features
**conhecidas até o meio do ano da colheita**: clima pelas **janelas fenológicas de
cada cultura** (café/laranja: florada set–nov e enchimento dez–mar; amendoim:
plantio out–dez e enchimento jan–mar; milho safrinha: fev–abr e abr–jun com geada
*dentro* do ciclo), defasagens do rendimento + **âncora** (média das safras de mesma
fase nas perenes; das últimas 3 nas anuais), capacidade (área ou pés), incentivo de
preço e anomalia de NDVI onde há máscara MapBiomas confiável.
**Validação leave-one-year-out** por cultura: o modelo nunca vê o ano que prevê;
erro comparado com persistência e lag-2. Faixas de incerteza = MAE por EDR.

### Sistema 1 — resposta rápida a eventos (café; extensível)
Detecção de geada no dia (limiar 6 °C na célula ~50 km ≈ 0 °C na relva, calibrado
em 2021) → ΔNDVI antes/depois restrito à cultura, com o não-cultivo como controle →
classes agronômicas → sacas e R$. Validado por dose-resposta e placebo no café.

### Limitações honestas
- Recorte municipal do IEA é apoio; a série oficial é por EDR.
- MapBiomas enxerga ~60% do café declarado e ~50% dos citros — usado para *localizar*, não *quantificar*.
- Amendoim e milho safrinha ainda **sem NDVI** (sem classe MapBiomas própria) — clima e histórico carregam o modelo.
- Perda pós-geada usa classes agronômicas com faixa ±50%.
- Clima em célula de ~50 km suaviza extremos locais.

*Código: [github.com/tbrena/previsao-safra](https://github.com/tbrena/previsao-safra).*
"""
    )
