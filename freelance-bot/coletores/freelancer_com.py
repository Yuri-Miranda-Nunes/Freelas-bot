"""Freelancer.com: API pública de projetos ativos (não exige login)."""
from datetime import datetime

from .base import Coletor, Projeto, html_para_texto, log

API = "https://www.freelancer.com/api/projects/0.1/projects/active/"


class ColetorFreelancer(Coletor):
    nome = "freelancer"

    def coletar(self) -> list[Projeto]:
        conf = self.cfg["plataformas"]["freelancer"]
        vistos: dict[str, Projeto] = {}
        for busca in self.cfg["buscas"]:
            params = {
                "query": busca,
                "limit": conf.get("limite_por_busca", 30),
                "full_description": "true",
                "job_details": "true",
                "sort_field": "time_updated",
            }
            try:
                dados = self.get(API, params=params).json()
            except Exception as e:
                log.warning("Freelancer.com: falha na busca '%s': %s", busca, e)
                continue
            for p in (dados.get("result") or {}).get("projects", []):
                proj = self._converter(p)
                if proj:
                    vistos.setdefault(proj.id_externo, proj)
        return list(vistos.values())

    @staticmethod
    def _converter(p: dict) -> Projeto | None:
        if p.get("status") != "active" or p.get("nonpublic"):
            return None
        jobs = p.get("jobs") or []
        categoria = ""
        if jobs and jobs[0].get("category"):
            categoria = jobs[0]["category"].get("name", "")
        orc = p.get("budget") or {}
        moeda = (p.get("currency") or {}).get("code", "USD")
        publicado = ""
        if p.get("time_submitted"):
            publicado = datetime.fromtimestamp(p["time_submitted"]).strftime("%d/%m/%Y %H:%M")
        return Projeto(
            plataforma="freelancer",
            id_externo=str(p["id"]),
            url=f"https://www.freelancer.com/projects/{p.get('seo_url', p['id'])}",
            titulo=p.get("title", ""),
            descricao=html_para_texto(p.get("description") or p.get("preview_description") or ""),
            categoria=categoria,
            habilidades=[j.get("name", "") for j in jobs],
            nivel_declarado=None,
            tipo="hora" if p.get("type") == "hourly" else "fixo",
            orcamento_min=orc.get("minimum"),
            orcamento_max=orc.get("maximum"),
            moeda=moeda,
            propostas=(p.get("bid_stats") or {}).get("bid_count"),
            publicado=publicado,
            idioma=p.get("language") or "en",
        )
