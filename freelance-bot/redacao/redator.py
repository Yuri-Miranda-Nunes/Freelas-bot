"""Gera o rascunho da proposta com evidências do portfólio, no idioma do projeto."""
from avaliacao import ia


def gerar_rascunho(cfg: dict, projeto: dict, avaliacao: ia.AvaliacaoIA, portfolio: str) -> str:
    return ia.redigir(cfg, projeto, avaliacao, portfolio)
