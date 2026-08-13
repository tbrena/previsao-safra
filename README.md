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
│   ├── config.py          # municípios, códigos SIDRA, áreas de interesse
│   └── dados/
│       ├── sidra.py       # rendimento oficial (IBGE PAM, tabela 1613)
│       ├── power.py       # clima diário (NASA POWER)
│       ├── satelite.py    # cenas Sentinel-2 + NDVI via STAC/COG
│       └── iea.py         # Estatísticas da Produção Paulista (IEA/CATI, por EDR)
├── scripts/
│   └── testar_fontes.py   # teste de fumaça das 3 fontes
├── notebooks/             # análises exploratórias
└── data/                  # raw/ e processed/ (fora do git)
```

## Como rodar

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python scripts\testar_fontes.py
```

## Roadmap

- [x] Coleta validada: IBGE SIDRA, NASA POWER, Sentinel-2 (STAC, leitura em janela)
- [x] IEA/CATI por EDR integrado (café 2020–2025; área nova como indicador antecedente)
- [ ] Exportar série IEA mais longa (idealmente 1990+) e/ou por município
- [ ] Máscara de café por município (MapBiomas classe 46)
- [ ] Série NDVI municipal 2000–2025 (MODIS/GEE) restrita à máscara de café
- [ ] Dataset municipal: features (NDVI, clima por janela fenológica, bienalidade) × ano
- [ ] Modelo baseline + validação leave-one-year-out; comparar com CONAB
- [ ] Previsão da safra 2026/27
- [ ] Expandir para soja/milho/cana

## Licença

A definir.
