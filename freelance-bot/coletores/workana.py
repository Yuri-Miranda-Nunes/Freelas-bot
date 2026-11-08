"""Workana: a listagem /jobs traz os projetos num JSON embutido (atributo results-initials)."""
import html
import json
import re
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .base import Coletor, Projeto, html_para_texto, interpretar_orcamento, log


class ColetorWorkana(Coletor):
    nome = "workana"

    def coletar(self) -> list[Projeto]:
        conf = self.cfg["plataformas"]["workana"]
        vistos: dict[str, Projeto] = {}
        for idioma in conf.get("idiomas", ["pt"]):
            for busca in self.cfg["buscas"]:
                for pagina in range(1, conf.get("paginas", 1) + 1):
                    params = {"language": idioma, "query": busca}
                    if pagina > 1:
                        params["page"] = pagina
                    url = "https://www.workana.com/jobs?" + urlencode(params)
                    try:
                        itens = self._extrair(self.get(url).text)
                    except Exception as e:
                        log.warning("Workana: falha em %s: %s", url, e)
                        break
                    for item in itens:
                        p = self._converter(item, idioma)
                        if p:
                            vistos.setdefault(p.id_externo, p)
                    if not itens:
                        break
        return list(vistos.values())

    @staticmethod
    def _extrair(pagina: str) -> list[dict]:
        m = re.search(r"results-initials='([^']*)'", pagina)
        if not m:
            raise ValueError("bloco results-initials não encontrado (layout mudou?)")
        return json.loads(html.unescape(m.group(1))).get("results", [])

    @staticmethod
    def _converter(r: dict, idioma: str) -> Projeto | None:
        slug = r.get("slug")
        if not slug:
            return None
        titulo_html = BeautifulSoup(r.get("title", ""), "html.parser")
        span = titulo_html.find("span", title=True)
        titulo = span["title"] if span else titulo_html.get_text(strip=True)

        desc_html = r.get("description", "")
        categoria = ""
        m_cat = re.search(r"Categor(?:ia|y):\s*<strong>(.*?)</strong>", desc_html)
        m_sub = re.search(r"Subcategor(?:ia|y):\s*<strong>(.*?)</strong>", desc_html)
        if m_cat:
            categoria = html.unescape(m_cat.group(1))
            if m_sub:
                categoria += " / " + html.unescape(m_sub.group(1))

        orc_txt = r.get("budget", "") or ""
        omin, omax, moeda = interpretar_orcamento(orc_txt, "USD")
        tipo = "hora" if r.get("isHourly") or "/h" in orc_txt or "hora" in orc_txt.lower() else "fixo"

        nota = None
        try:
            nota = float((r.get("rating") or {}).get("value"))
        except (TypeError, ValueError):
            pass
        propostas = None
        m_prop = re.search(r"(\d+)", r.get("totalBids", "") or "")
        if m_prop:
            propostas = int(m_prop.group(1))

        return Projeto(
            plataforma="workana",
            id_externo=slug,
            url=f"https://www.workana.com/job/{slug}",
            titulo=titulo,
            descricao=html_para_texto(desc_html),
            categoria=categoria,
            habilidades=[s.get("anchorText", "") for s in r.get("skills") or []],
            nivel_declarado=None,  # Workana não declara nível na listagem
            tipo=tipo,
            orcamento_min=omin,
            orcamento_max=omax,
            moeda=moeda,
            cliente_nota=nota if nota and nota > 0 else None,
            cliente_avaliacoes=None,
            cliente_pagamento_verificado=bool(r.get("hasVerifiedPaymentMethod")),
            propostas=propostas,
            publicado=r.get("postedDate", ""),
            idioma=idioma,
        )
