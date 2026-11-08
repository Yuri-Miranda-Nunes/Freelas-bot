"""Lê o portfólio do usuário (dados/portfolio.md)."""
import logging

from config import CAMINHO_PORTFOLIO

log = logging.getLogger("portfolio")
MARCADOR_MODELO = "<!-- MODELO: substitua este arquivo -->"


def carregar() -> str:
    if not CAMINHO_PORTFOLIO.exists():
        raise FileNotFoundError(f"Portfólio não encontrado em {CAMINHO_PORTFOLIO}")
    texto = CAMINHO_PORTFOLIO.read_text(encoding="utf-8")
    if MARCADOR_MODELO in texto:
        log.warning("dados/portfolio.md ainda é o modelo. Preencha com seus dados reais "
                    "para avaliações e propostas melhores.")
    return texto
