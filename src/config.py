"""Configurações do projeto: municípios, códigos SIDRA e áreas de interesse.

Códigos IBGE verificados na API de localidades em 12/08/2026.
"""

# Municípios cafeeiros de referência (código IBGE -> nome)
MUNICIPIOS_CAFE = {
    # Sul de Minas (arábica)
    "3170701": "Varginha (MG)",
    "3128709": "Guaxupé (MG)",
    "3169406": "Três Pontas (MG)",
    "3101607": "Alfenas (MG)",
    # Cerrado Mineiro (arábica, irrigado)
    "3148103": "Patrocínio (MG)",
    "3143104": "Monte Carmelo (MG)",
    # Matas de Minas (arábica de montanha)
    "3139409": "Manhuaçu (MG)",
    # Alta Mogiana (arábica)
    "3516200": "Franca (SP)",
    # Espírito Santo (conilon/canephora)
    "3203056": "Jaguaré (ES)",
    "3203908": "Nova Venécia (ES)",
    "3203205": "Linhares (ES)",
}

# Centroides aproximados (lat, lon) para consulta de clima (célula ~50 km)
COORDENADAS = {
    "3170701": (-21.55, -45.43),  # Varginha
    "3128709": (-21.31, -46.71),  # Guaxupé
    "3169406": (-21.37, -45.51),  # Três Pontas
    "3101607": (-21.43, -45.95),  # Alfenas
    "3148103": (-18.94, -46.99),  # Patrocínio
    "3143104": (-18.73, -47.50),  # Monte Carmelo
    "3139409": (-20.26, -42.03),  # Manhuaçu
    "3516200": (-20.54, -47.40),  # Franca
    "3203056": (-18.91, -40.08),  # Jaguaré
    "3203908": (-18.71, -40.40),  # Nova Venécia
    "3203205": (-19.39, -40.07),  # Linhares
}

# Produto na classificação c82 da tabela 1613 (PAM, lavouras permanentes)
CAFE_TOTAL = "2723"      # Café (em grão) Total — série desde 1974
CAFE_ARABICA = "31619"   # desagregado a partir de 2012
CAFE_CANEPHORA = "31620" # desagregado a partir de 2012

# Área de exemplo para NDVI: zona cafeeira em torno de Guaxupé/MG
# bbox = (oeste, sul, leste, norte), graus decimais WGS84
AOI_GUAXUPE = (-46.76, -21.36, -46.68, -21.28)
