"""Carrega config.json e segredos.json (este último fica fora do controle de versão)."""
import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA_CONFIG = RAIZ / "config"
PASTA_DADOS = RAIZ / "dados"
PASTA_LOGS = RAIZ / "logs"
CAMINHO_BANCO = PASTA_DADOS / "projetos.db"
CAMINHO_PORTFOLIO = PASTA_DADOS / "portfolio.md"


def carregar_config() -> dict:
    with open(PASTA_CONFIG / "config.json", encoding="utf-8") as f:
        return json.load(f)


def carregar_segredos() -> dict:
    caminho = PASTA_CONFIG / "segredos.json"
    segredos = {}
    if caminho.exists():
        with open(caminho, encoding="utf-8") as f:
            segredos = json.load(f)
    # Variáveis de ambiente têm prioridade sobre o arquivo
    if os.environ.get("ANTHROPIC_API_KEY"):
        segredos["anthropic_api_key"] = os.environ["ANTHROPIC_API_KEY"]
    return segredos


def configurar_log(nome: str = "bot") -> logging.Logger:
    PASTA_LOGS.mkdir(exist_ok=True)
    raiz = logging.getLogger()
    if not raiz.handlers:
        raiz.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        arq = RotatingFileHandler(PASTA_LOGS / f"{nome}.log", maxBytes=2_000_000,
                                  backupCount=3, encoding="utf-8")
        arq.setFormatter(fmt)
        raiz.addHandler(arq)
        if sys.stderr is not None:          # pythonw (agendador) não tem console
            for fluxo in (sys.stdout, sys.stderr):
                try:
                    fluxo.reconfigure(encoding="utf-8", errors="replace")
                except (AttributeError, ValueError):
                    pass
            tela = logging.StreamHandler()
            tela.setFormatter(fmt)
            raiz.addHandler(tela)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpx2").setLevel(logging.WARNING)
    return logging.getLogger(nome)
