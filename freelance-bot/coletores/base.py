"""Formato comum de projeto e utilidades compartilhadas pelos coletores."""
import html
import logging
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

import requests
from bs4 import BeautifulSoup

log = logging.getLogger("coletores")

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")


@dataclass
class Projeto:
    plataforma: str
    id_externo: str
    url: str
    titulo: str
    descricao: str
    categoria: str = ""
    habilidades: list = field(default_factory=list)
    nivel_declarado: Optional[str] = None      # iniciante | intermediario | avancado | None
    tipo: str = "fixo"                          # fixo | hora
    orcamento_min: Optional[float] = None
    orcamento_max: Optional[float] = None
    moeda: str = "BRL"
    cliente_nota: Optional[float] = None        # 0 a 5
    cliente_avaliacoes: Optional[int] = None
    cliente_pagamento_verificado: Optional[bool] = None
    propostas: Optional[int] = None
    publicado: str = ""
    idioma: str = "pt"

    def dict(self) -> dict:
        return asdict(self)


class Coletor:
    nome = "base"

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.atraso = cfg.get("atraso_entre_requisicoes_seg", 4)
        self.sessao = requests.Session()
        self.sessao.headers.update({"User-Agent": USER_AGENT,
                                    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"})
        self._ultima = 0.0

    def get(self, url: str, **kw) -> requests.Response:
        espera = self.atraso - (time.time() - self._ultima)
        if espera > 0:
            time.sleep(espera)
        self._ultima = time.time()
        r = self.sessao.get(url, timeout=30, **kw)
        r.raise_for_status()
        return r

    def coletar(self) -> list[Projeto]:
        raise NotImplementedError

    def completar(self, projeto: Projeto) -> Projeto:
        """Busca detalhes extras (ex.: orçamento na página do projeto). Padrão: nada."""
        return projeto


def html_para_texto(conteudo: str) -> str:
    if not conteudo:
        return ""
    texto = BeautifulSoup(html.unescape(conteudo), "html.parser").get_text("\n")
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


_MOEDAS = [("R$", "BRL"), ("BRL", "BRL"), ("USD", "USD"), ("US$", "USD"),
           ("EUR", "EUR"), ("€", "EUR"), ("GBP", "GBP"), ("£", "GBP")]


def _numero(txt: str) -> float:
    """Converte '1.500,00', '1,500.00', '3.000' ou '250' em float."""
    txt = txt.strip()
    if "," in txt and "." in txt:
        if txt.rfind(",") > txt.rfind("."):
            txt = txt.replace(".", "").replace(",", ".")
        else:
            txt = txt.replace(",", "")
    elif "," in txt:
        partes = txt.split(",")
        txt = txt.replace(",", "." if len(partes[-1]) != 3 else "")
    elif "." in txt and len(txt.split(".")[-1]) == 3:
        txt = txt.replace(".", "")
    return float(txt)


def interpretar_orcamento(texto: str, moeda_padrao: str = "BRL"):
    """'USD 100 - 250' -> (100, 250, 'USD'); 'Menos de USD 50' -> (None, 50, 'USD')."""
    if not texto:
        return None, None, moeda_padrao
    moeda = moeda_padrao
    for marca, codigo in _MOEDAS:
        if marca in texto:
            moeda = codigo
            break
    numeros = [_numero(n) for n in re.findall(r"\d[\d.,]*", texto)]
    baixo = texto.lower()
    if not numeros:
        return None, None, moeda
    if any(p in baixo for p in ("menos de", "less than", "até", "up to")):
        return None, numeros[0], moeda
    if any(p in baixo for p in ("mais de", "more than", "over", "acima de")):
        return numeros[0], None, moeda
    if len(numeros) == 1:
        return numeros[0], numeros[0], moeda
    return numeros[0], numeros[1], moeda
