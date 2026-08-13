# Previsão de Safra

Previsão de produtividade agrícola no Brasil — começando pelo **café** — usando
satélites gratuitos, clima e estatísticas oficiais como verdade de campo.

## Abordagem

Previsão em **nível municipal**, treinada contra o rendimento oficial do IBGE:

```
NDVI/EVI (satélite)  ─┐
Clima da janela crítica├─→  modelo supervisionado  ─→  rendimento previsto (kg/ha)
Bienalidade do café  ─┘      (RF/XGBoost, depois LSTM)     antes da colheita
```

- **Janelas críticas do café:** florada (set–nov) e enchimento do grão (dez–mar).
  Chuva/seca na florada é o maior driver do ano seguinte.
- **Bienalidade:** o cafeeiro alterna anos de carga alta e baixa — o rendimento
  do ano anterior entra como feature. Visível nos dados reais de Varginha/MG:
  1900 kg/ha (2020) → 1200 (2021) → 1020 (2022, pós-geada) → 1680 (2023).

## Fontes de dados gratuitas

Testadas em 12/08/2026. "Sem cadastro" = funciona direto, sem criar conta.

| Fonte | O que fornece | Resolução | Acesso |
|---|---|---|---|
| **Sentinel-2** (ESA) | NDVI/EVI por talhão | 10 m, ~5 dias | STAC `earth-search` (AWS), sem cadastro ✅ |
| **NASA POWER** | clima diário desde 1981 (chuva, temp., radiação, UR) | ~50 km | API sem cadastro ✅ |
| **IBGE PAM** (SIDRA) | rendimento/área/produção municipal 1974–**2024** | município/ano | API sem cadastro ✅ |
| Landsat 8/9 (NASA/USGS) | série óptica longa (desde 1984) | 30 m, 16 dias | Planetary Computer / USGS |
| MODIS → VIIRS (NASA) | NDVI quase diário desde 2000 — ideal p/ escala municipal | 250–500 m | AppEEARS (conta Earthdata gratuita) |
| Sentinel-1 (ESA) | radar — enxerga através de nuvens (florada é época chuvosa) | 10 m | mesmo STAC |
| CBERS-4A / Amazônia-1 (INPE) | óptico brasileiro | 2–8 m | catálogo INPE, gratuito |
| CHIRPS | chuva de alta qualidade desde 1981 | ~5 km | download aberto |
| CONAB | 4 levantamentos de café/ano, séries por UF | UF | planilhas abertas |
| MapBiomas | **máscara de onde há café** (classe 46), soja, cana etc. | 30 m, anual | download / Earth Engine |
| **IEA/CATI — SAAESP** | levantamentos de SP por EDR: área nova, área em produção, produção (~90 produtos, café incluso) — **inclui o ano corrente**, antes do IBGE | EDR/ano | export do banco IEA (temos 2020–2025 em `data/raw/iea/`) ✅ |

Para séries NDVI municipais completas em escala (todos os municípios, 20+ anos),
os caminhos práticos são **Google Earth Engine** (gratuito p/ uso não comercial,
exige conta Google) ou **MODIS via AppEEARS**. O Brazil Data Cube (INPE) é
alternativa nacional.

## Culturas viáveis com satélite gratuito

- **Café arábica** (Sul de Minas, Cerrado Mineiro, Mogiana) e **conilon** (ES) — alvo
  inicial. É a cultura *mais difícil* (perene, dossel sempre verde, bienalidade):
  o satélite captura vigor/estresse, e clima + bienalidade fazem o resto.
- **Soja, milho (1ª e 2ª safra), cana, algodão, arroz, trigo** — anuais, nos quais
  NDVI ↔ rendimento é bem mais direto; expansão natural do projeto.

## Estrutura

```
previsao-safra/
├── src/
│   ├── config.py          # caminhos, municípios, códigos SIDRA
│   ├── eventos.py         # detector de geada/seca (Sistema 1)
│   ├── dano.py            # ΔNDVI sobre o café, controle não-café (Sistema 1)
│   ├── perda.py           # classes de dano → sacas e R$ (Sistema 1)
│   ├── nowcast.py         # dataset EDR×ano + modelo de rendimento (Sistema 2)
│   └── dados/
│       ├── iea.py         # produção/EDR, VPA, preços, salários, colheita (IEA/CATI)
│       ├── sidra.py       # rendimento oficial municipal (IBGE PAM t1613)
│       ├── power.py       # clima diário (NASA POWER)
│       ├── satelite.py    # Sentinel-2 via STAC/COG
│       ├── mapbiomas.py   # máscara de café (classe 46) e células por EDR
│       ├── geo.py         # shapes dos 40 EDRs CATI + 16 RAs
│       └── util.py        # chave de junção normalizada
├── scripts/
│   ├── testar_fontes.py   # teste de fumaça das fontes
│   ├── avaliar_geada.py   # Sistema 1: clima → ΔNDVI → sacas → R$
│   └── rodar_nowcast.py   # Sistema 2: dataset → validação LOYO → previsão
├── app/
│   └── painel.py          # painel Streamlit (apresentação e uso)
├── relatorios/            # backtests e boletins versionados
└── data/                  # raw/ e processed/ (fora do git)
```

## Como rodar

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python scripts\testar_fontes.py     # valida as fontes
.venv\Scripts\python scripts\rodar_nowcast.py     # gera previsão + métricas
.venv\Scripts\streamlit run app\painel.py         # abre o painel
.venv\Scripts\python scripts\avaliar_geada.py     # varredura de geada (inverno)
```

## Roadmap

- [x] Coleta validada: IBGE SIDRA, NASA POWER, Sentinel-2 (STAC, leitura em janela)
- [x] IEA/CATI integrado: produção EDR 2010–2025, municípios (QA), VPA, preços 1948+, salários, colheita
- [x] Shapes dos 40 EDRs (CATI 2022) + chave de junção normalizada
- [x] Máscara de café MapBiomas (683 células, ~98 mil ha) por EDR
- [x] **Sistema 1** — resposta rápida a geada: detector calibrado (2021) + ΔNDVI com controle + sacas/R$; validado por dose-resposta e placebo (`relatorios/backtest_geada_jul2021.md`)
- [x] **Sistema 2** — nowcast por EDR: clima fenológico + bienalidade + área + preço, validação leave-one-year-out, previsão 2026
- [x] Painel Streamlit (previsão, séries, monitor de geada, metodologia)
- [ ] Exportar série IEA 1983–2009 para esticar o treino
- [ ] NDVI mensal por EDR como covariável do nowcast (GEE/MODIS)
- [ ] Boletim mensal automatizado + comparação com levantamentos IEA/CONAB
- [ ] Expandir para soja/milho/cana (IEA já cobre ~90 produtos)

## Licença

A definir.
