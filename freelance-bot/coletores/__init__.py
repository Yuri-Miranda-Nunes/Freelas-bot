from .base import Coletor, Projeto
from .freelancer_com import ColetorFreelancer
from .freelas99 import Coletor99Freelas
from .upwork import ColetorUpwork
from .workana import ColetorWorkana

COLETORES = {
    "workana": ColetorWorkana,
    "99freelas": Coletor99Freelas,
    "freelancer": ColetorFreelancer,
    "upwork": ColetorUpwork,
}


def coletores_ativos(cfg: dict) -> list[Coletor]:
    return [cls(cfg) for nome, cls in COLETORES.items()
            if cfg["plataformas"].get(nome, {}).get("ativo")]
