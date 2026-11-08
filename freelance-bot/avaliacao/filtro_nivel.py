"""Filtros antes da IA: palavras-chave e nível declarado."""
import re
import unicodedata


def _normalizar(t: str) -> str:
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()


def _compilar(termos):
    return [re.compile(r"(?<![a-z0-9])" + re.escape(_normalizar(t)) + r"(?![a-z0-9])") for t in termos]


class FiltroPalavras:
    def __init__(self, cfg: dict):
        self.incluir = _compilar(cfg["palavras_chave"])
        self.excluir = _compilar(cfg.get("palavras_excluir", []))

    def aceita(self, titulo: str, descricao: str, habilidades: list) -> tuple[bool, list[str]]:
        texto = _normalizar(" ".join([titulo, descricao, " ".join(habilidades)]))
        if any(p.search(texto) for p in self.excluir):
            return False, []
        achadas = [p.pattern for p in self.incluir if p.search(texto)]
        return bool(achadas), achadas


def nivel_permitido(nivel_declarado: str | None) -> bool:
    """Avançado declarado é descartado. Iniciante, intermediário e não declarado seguem;
    intermediário passa por regras extras na nota (ver nota.py)."""
    return nivel_declarado != "avancado"
