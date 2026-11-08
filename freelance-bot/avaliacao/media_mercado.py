"""Média de remuneração por plataforma e categoria, a partir de todos os projetos coletados."""
from datetime import datetime, timedelta

from dados import armazenamento as db


def media(cfg: dict, plataforma: str, categoria: str, tipo: str):
    """Devolve (média_brl, origem) ou (None, motivo). Cai para a média da plataforma se a
    categoria tiver poucas amostras."""
    ap = cfg["aprovacao"]
    desde = (datetime.now() - timedelta(days=ap["dias_media_mercado"])).isoformat()
    minimo = ap["amostras_minimas_media"]

    m, n = db.media_amostras(plataforma, categoria, tipo, desde)
    if m is not None and n >= minimo:
        return m, f"média de {n} projetos em {plataforma} / {categoria or 'sem categoria'}"
    m, n = db.media_amostras(plataforma, None, tipo, desde)
    if m is not None and n >= minimo:
        return m, f"média de {n} projetos em {plataforma} (categoria com poucas amostras)"
    return None, "amostras insuficientes"
