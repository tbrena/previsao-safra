# Backtest — Geada de julho/2021 no café paulista

*Gerado em 13/08/2026 pelo Sistema 1 (previsao-safra). Dados: NASA POWER,
Sentinel-2 (earth-search/AWS), MapBiomas Coleção 9, IEA/CATI.*

## 1. Detecção no clima (NASA POWER, T2M_MIN por centroide de EDR)

Três ondas de frio capturadas: **30/06–01/07**, **19–20/07** e **29–31/07**.
Mínimas na célula (~50 km): Avaré 0,9 °C · Botucatu 1,4 °C · Ourinhos 1,8 °C ·
SJBV 2,0 °C · Marília 3,3 °C · Franca 4,5 °C. (Relvado ≈ abrigo − 4 a 6 °C.)

## 2. Dano por ΔNDVI (compostos medianos ~44 m, café MapBiomas, fundo não-café como controle)

| EDR | T2M_MIN | % área queda forte (≥0,15) | % moderada (≥0,10) | Placebo 2019 (forte/mod.) |
|---|---|---|---|---|
| Ourinhos | 1,8 | 11,0 | 20,3 | 2,8 / 5,6 |
| Avaré | 0,9 | 10,2 | 17,0 | — |
| São João da Boa Vista | 2,0 | 7,2 | 14,7 | — |
| Franca | 4,5 | 3,7 | 7,1 | — |
| Marília | 3,3 | 2,7 | 6,1 | — |

**Dose-resposta validada:** EDRs com célula ≤ 2 °C mostram cauda de dano 2,5–4×
o placebo; acima de ~3 °C o café fica indistinguível do fundo. No inverno
normal (placebo 2019) o café cai *menos* que o fundo (excesso +0,016); na
geada, inverte.

## 3. Perda estimada (classes agronômicas: forte 70%, moderada 35%, leve 15% · ±50%)

Base de produção: IEA 2020 (último ano de carga alta). Preço: média 2022
(R$ 1.267,95/sc, recebido pelo produtor).

| EDR | Perda % | Sacas perdidas | R$ (preço médio 2022) |
|---|---|---|---|
| São João da Boa Vista | 6,9% | 94.537 | R$ 119,9 mi |
| Franca | 1,4% | 39.726 | R$ 50,4 mi |
| Ourinhos | 9,2% | 33.178 | R$ 42,1 mi |
| Avaré | 7,2% | 11.038 | R$ 14,0 mi |
| Marília | 0,3% | 1.680 | R$ 2,1 mi |
| **Total (5 EDRs)** | — | **180.159** [89–269 mil] | **R$ 228 mi** [113–341] |

## 4. Confronto com o realizado — e limites honestos

SP produziu 6,36 M sc (2020) → 4,43 M sc (2022): queda de 1,93 M sc. A perda
**diretamente visível por satélite** (queima de dossel) responde por ~10% disso;
o restante veio da seca 2020–21 (florada de Franca: −63% de chuva), da poda
pós-geada (esqueletamento zera 1–2 safras) e da fase bienal — fatores que a
regressão linear dano→perda com 5 pontos não separa (k≈0 no ajuste).

**O que o sistema entrega com confiança:** detecção do evento no dia, mapa
graduado de dano por EDR ~2 semanas depois (validado por dose-resposta e
placebo), e ordem de grandeza da perda direta com faixa explícita.
**O que exige o Sistema 2 (nowcast):** atribuição completa da quebra, com
seca, bienalidade, área e preço como covariáveis.

## Reprodução

```bash
.venv\Scripts\python scripts\avaliar_geada.py --inicio 2021-07-15 --fim 2021-08-05
```
