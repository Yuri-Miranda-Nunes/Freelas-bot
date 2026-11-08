"""Upwork: sem coleta automática.

O Upwork desligou os feeds RSS em 2024, exige login para ver as listagens e os
termos de uso proíbem raspagem. O caminho oficial é a API GraphQL do Upwork,
que exige solicitar uma chave de API aprovada pela própria plataforma.
Quando você tiver essa chave, implemente coletar() aqui devolvendo Projeto(...).
"""
from .base import Coletor, Projeto, log


class ColetorUpwork(Coletor):
    nome = "upwork"

    def coletar(self) -> list[Projeto]:
        log.info("Upwork: coletor desativado (requer API oficial do Upwork).")
        return []
