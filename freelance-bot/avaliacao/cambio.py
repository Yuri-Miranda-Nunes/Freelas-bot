"""Cotação do dia para converter orçamentos em R$. Busca uma vez por dia e guarda no banco."""
import logging
from datetime import date

import requests

from dados import armazenamento as db

log = logging.getLogger("cambio")


class Cambio:
    def __init__(self, cfg: dict):
        self.cfg = cfg["cambio"]
        self.taxas = self._carregar()

    def _carregar(self) -> dict:
        hoje = date.today().isoformat()
        taxas = db.cambio_do_dia(hoje)
        if taxas:
            return taxas
        taxas = dict(self.cfg["fallback"])
        try:
            r = requests.get(self.cfg["fonte"], timeout=20)
            r.raise_for_status()
            for chave, v in r.json().items():          # ex.: "USDBRL": {"bid": "5.41", ...}
                taxas[chave.replace("BRL", "")] = float(v["bid"])
            db.salvar_cambio(hoje, taxas)
            log.info("Câmbio do dia: %s", {k: round(v, 3) for k, v in taxas.items()})
        except Exception as e:
            log.warning("Falha ao buscar câmbio, usando valores de fallback: %s", e)
        taxas["BRL"] = 1.0
        return taxas

    def para_brl(self, valor, moeda: str):
        if valor is None:
            return None
        taxa = self.taxas.get((moeda or "BRL").upper())
        if taxa is None:
            log.warning("Moeda sem cotação: %s", moeda)
            return None
        return float(valor) * taxa


def valor_representativo(omin, omax):
    """Um número para comparar faixas: média da faixa; só mínimo -> mínimo; só máximo -> 75% dele."""
    if omin is not None and omax is not None:
        return (omin + omax) / 2
    if omin is not None:
        return omin
    if omax is not None:
        return omax * 0.75
    return None
