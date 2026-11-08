"""Executa uma rodada completa: coletar -> filtrar -> avaliar -> redigir -> salvar -> notificar.

Uso:
    python orquestrador.py              rodada completa
    python orquestrador.py --sem-ia     só coleta e filtra (projetos ficam pendentes)
    python orquestrador.py --sem-email  rodada completa sem enviar e-mail
    python orquestrador.py --teste-email  envia um e-mail de teste e sai
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from avaliacao import avaliador, ia, nota  # noqa: E402
from avaliacao.cambio import Cambio, valor_representativo  # noqa: E402
from avaliacao.filtro_nivel import FiltroPalavras, nivel_permitido  # noqa: E402
from coletores import coletores_ativos  # noqa: E402
from config import PASTA_DADOS, carregar_config, configurar_log  # noqa: E402
from dados import armazenamento as db  # noqa: E402
from notificacao import notificador  # noqa: E402
from redacao import portfolio, redator  # noqa: E402

log = configurar_log("bot")
TRAVA = PASTA_DADOS / "rodada.lock"


def _travar() -> bool:
    PASTA_DADOS.mkdir(exist_ok=True)
    if TRAVA.exists() and time.time() - TRAVA.stat().st_mtime < 90 * 60:
        return False
    TRAVA.write_text(str(os.getpid()))
    return True


def _linha_para_dict(r) -> dict:
    d = dict(r)
    d["habilidades"] = json.loads(d["habilidades"] or "[]")
    v = d["cliente_pagamento_verificado"]
    d["cliente_pagamento_verificado"] = None if v is None else bool(v)
    return d


def _texto_orcamento(p: dict, valor_brl) -> str:
    if p["orcamento_min"] is None and p["orcamento_max"] is None:
        return "não informado"
    faixa = " a ".join(f"{v:,.0f}" for v in (p["orcamento_min"], p["orcamento_max"]) if v is not None)
    sufixo = "/hora" if p["tipo"] == "hora" else ""
    brl = f" (≈ R$ {valor_brl:,.0f}{sufixo})" if valor_brl is not None and p["moeda"] != "BRL" else ""
    return f"{p['moeda']} {faixa}{sufixo}{brl}"


def coletar(cfg: dict, cambio: Cambio) -> tuple[int, int]:
    filtro = FiltroPalavras(cfg)
    total = novos = 0
    for coletor in coletores_ativos(cfg):
        try:
            projetos = coletor.coletar()
        except Exception:
            log.exception("Coletor %s falhou", coletor.nome)
            continue
        log.info("%s: %d projetos lidos", coletor.nome, len(projetos))
        total += len(projetos)
        for p in projetos:
            valor = cambio.para_brl(valor_representativo(p.orcamento_min, p.orcamento_max), p.moeda)
            db.registrar_amostra(p.plataforma, p.id_externo, p.categoria, p.tipo, valor)

            ok, _ = filtro.aceita(p.titulo, p.descricao, p.habilidades)
            if not ok or db.ja_visto(p.plataforma, p.id_externo):
                continue
            if nivel_permitido(p.nivel_declarado):
                p = coletor.completar(p)
                valor = cambio.para_brl(valor_representativo(p.orcamento_min, p.orcamento_max), p.moeda)
                db.registrar_amostra(p.plataforma, p.id_externo, p.categoria, p.tipo, valor)

            pid = db.inserir_projeto(p.dict(), valor)
            novos += 1
            if not nivel_permitido(p.nivel_declarado):
                db.salvar_avaliacao(pid, "reprovado", {}, None,
                                    ["nível declarado: avançado"], None)
    return total, novos


def avaliar_pendentes(cfg: dict) -> tuple[int, list[dict]]:
    fila = db.pendentes(cfg["ia"]["max_avaliacoes_por_rodada"])
    if not fila:
        return 0, []
    texto_portfolio = portfolio.carregar()
    avaliados, aprovados = 0, []
    for linha in fila:
        p = _linha_para_dict(linha)
        valor = p["orcamento_brl"]
        try:
            av = ia.avaliar(cfg, p, texto_portfolio, _texto_orcamento(p, valor))
            notas, detalhes = avaliador.avaliar_partes(cfg, p, valor, av)
            aprovado, motivos = nota.decidir(cfg, p, notas, detalhes, av)
            rascunho = redator.gerar_rascunho(cfg, p, av, texto_portfolio) if aprovado else None
        except ia.ErroIA as e:
            log.error("Projeto %s (%s): %s", p["id"], p["titulo"][:60], e)
            db.registrar_erro(p["id"], str(e))
            if "Chave" in str(e) or "Limite" in str(e) or "conexão" in str(e):
                break   # não adianta tentar os próximos agora
            continue

        registro = av.model_dump() | {"criterios": detalhes, "modelo_usado": ia.ultimo_modelo}
        status = "novo" if aprovado else "reprovado"
        db.salvar_avaliacao(p["id"], status, notas, registro, motivos, rascunho)
        avaliados += 1
        log.info("[%s] %5.1f  %s  %s", status.upper(), notas["total"], p["plataforma"], p["titulo"][:70])
        if aprovado:
            aprovados.append(p | {"nota_total": notas["total"]})
    return avaliados, aprovados


def main():
    ap = argparse.ArgumentParser(description="Rodada do bot de projetos freelance")
    ap.add_argument("--sem-ia", action="store_true")
    ap.add_argument("--sem-email", action="store_true")
    ap.add_argument("--teste-email", action="store_true")
    args = ap.parse_args()

    cfg = carregar_config()
    db.iniciar()

    if args.teste_email:
        ok = notificador.enviar("[Freelance bot] teste", "E-mail de teste do bot.",
                                "<p>E-mail de teste do bot.</p>")
        sys.exit(0 if ok else 1)

    if not _travar():
        log.warning("Outra rodada ainda está em andamento; saindo.")
        return
    inicio = db.agora()
    try:
        log.info("=== Rodada iniciada ===")
        cambio = Cambio(cfg)
        coletados, novos = coletar(cfg, cambio)
        log.info("Coleta: %d lidos, %d novos com palavras-chave", coletados, novos)

        avaliados, aprovados = (0, [])
        if not args.sem_ia:
            avaliados, aprovados = avaliar_pendentes(cfg)

        if aprovados and cfg["notificacao"]["ativo"] and not args.sem_email:
            notificador.notificar_aprovados(cfg, aprovados)

        resumo = f"{coletados} lidos, {novos} novos, {avaliados} avaliados, {len(aprovados)} aprovados"
        db.registrar_rodada(inicio, db.agora(), coletados, novos, avaliados, len(aprovados), resumo)
        log.info("=== Rodada concluída: %s ===", resumo)
    except Exception:
        log.exception("Rodada interrompida por erro")
        db.registrar_rodada(inicio, db.agora(), 0, 0, 0, 0, "erro (ver logs/bot.log)")
        raise
    finally:
        TRAVA.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
