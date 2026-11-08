"""99Freelas: listagem em HTML (/projects?q=...). Orçamento só aparece na página do projeto."""
import html
import re
import unicodedata
from datetime import datetime
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup

from .base import Coletor, Projeto, html_para_texto, interpretar_orcamento, log

BASE = "https://www.99freelas.com.br"


def _sem_acento(t: str) -> str:
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()


def _nivel(texto: str):
    t = _sem_acento(texto)
    if "iniciante" in t:
        return "iniciante"
    if "intermediario" in t:
        return "intermediario"
    if "especialista" in t or "avancado" in t or "experiente" in t:
        return "avancado"
    return None


class Coletor99Freelas(Coletor):
    nome = "99freelas"

    def coletar(self) -> list[Projeto]:
        conf = self.cfg["plataformas"]["99freelas"]
        vistos: dict[str, Projeto] = {}
        for busca in self.cfg["buscas"]:
            for pagina in range(1, conf.get("paginas", 1) + 1):
                params = {"q": busca}
                if pagina > 1:
                    params["page"] = pagina
                url = f"{BASE}/projects?" + urlencode(params)
                try:
                    r = self.get(url)
                    r.encoding = r.apparent_encoding or "utf-8"
                    itens = self._extrair(r.text)
                except Exception as e:
                    log.warning("99Freelas: falha em %s: %s", url, e)
                    break
                for p in itens:
                    vistos.setdefault(p.id_externo, p)
                if not itens:
                    break
        return list(vistos.values())

    def _extrair(self, pagina: str) -> list[Projeto]:
        sopa = BeautifulSoup(pagina, "html.parser")
        projetos = []
        for li in sopa.select("li.result-item[data-id]"):
            link = li.select_one("h1.title a")
            if not link:
                continue
            info = li.select_one("p.information")
            info_txt = info.get_text(" ", strip=True) if info else ""
            partes = [x.strip() for x in info_txt.split("|")]
            categoria = partes[0] if partes else ""

            publicado = ""
            dt = info.select_one("b.datetime[cp-datetime]") if info else None
            if dt:
                try:
                    publicado = datetime.fromtimestamp(int(dt["cp-datetime"]) / 1000).strftime("%d/%m/%Y %H:%M")
                except ValueError:
                    pass
            propostas = None
            m = re.search(r"Propostas:\s*(\d+)", info_txt)
            if m:
                propostas = int(m.group(1))

            desc = li.select_one("div.description")
            descricao = html_para_texto(desc.get("data-content", "")) if desc else ""
            if not descricao and desc:
                descricao = desc.get_text("\n", strip=True)

            estrela = li.select_one("span.avaliacoes-star")
            nota = None
            if estrela and estrela.get("data-score"):
                try:
                    nota = float(estrela["data-score"]) or None
                except ValueError:
                    pass
            aval_txt = li.select_one("span.avaliacoes-text")
            n_aval = 0
            if aval_txt:
                m = re.search(r"(\d+)", aval_txt.get_text())
                n_aval = int(m.group(1)) if m else 0

            projetos.append(Projeto(
                plataforma="99freelas",
                id_externo=li["data-id"],
                url=urljoin(BASE, link["href"].split("?")[0]),
                titulo=html.unescape(li.get("data-nome") or link.get_text(strip=True)),
                descricao=descricao,
                categoria=categoria,
                habilidades=[a.get_text(strip=True) for a in li.select("a.habilidade")],
                nivel_declarado=_nivel(info_txt),
                tipo="fixo",
                moeda="BRL",
                cliente_nota=nota,
                cliente_avaliacoes=n_aval,
                cliente_pagamento_verificado=None,
                propostas=propostas,
                publicado=publicado,
                idioma="pt",
            ))
        return projetos

    def completar(self, projeto: Projeto) -> Projeto:
        try:
            r = self.get(projeto.url)
            r.encoding = r.apparent_encoding or "utf-8"
        except Exception as e:
            log.warning("99Freelas: sem detalhes de %s: %s", projeto.url, e)
            return projeto
        sopa = BeautifulSoup(r.text, "html.parser")
        campos = {}
        for tr in sopa.select("tr"):
            th, td = tr.find("th"), tr.find("td")
            if th and td:
                campos[_sem_acento(th.get_text(strip=True)).rstrip(":")] = td.get_text(" ", strip=True)

        orc = campos.get("orcamento", "")
        if orc and "aberto" not in _sem_acento(orc):
            omin, omax, _ = interpretar_orcamento(orc, "BRL")
            projeto.orcamento_min, projeto.orcamento_max = omin, omax
        elif campos.get("valor minimo"):
            omin, _, _ = interpretar_orcamento(campos["valor minimo"], "BRL")
            projeto.orcamento_min = omin
        if not projeto.nivel_declarado and campos.get("nivel de experiencia"):
            projeto.nivel_declarado = _nivel(campos["nivel de experiencia"])
        return projeto
