"""Calcula as partes da nota: orçamento, histórico do cliente e balanceamento
(dificuldade real + remuneração vs média da plataforma e categoria)."""
from . import media_mercado
from .ia import AvaliacaoIA


def _limitar(x: float) -> float:
    return max(0.0, min(1.0, x))


def nota_orcamento(cfg: dict, valor_total_brl) -> tuple[float, str]:
    peso = cfg["pesos"]["orcamento"]
    o = cfg["orcamento"]
    if valor_total_brl is None:
        return round(peso * 0.3, 1), "orçamento não informado (nota neutra baixa)"
    frac = _limitar((valor_total_brl - o["minimo_brl"]) / (o["ideal_brl"] - o["minimo_brl"]))
    return round(peso * frac, 1), f"≈ R$ {valor_total_brl:,.0f} (mín. R$ {o['minimo_brl']}, ideal R$ {o['ideal_brl']})"


def nota_cliente(cfg: dict, p: dict) -> tuple[float, str]:
    peso = cfg["pesos"]["cliente"]
    nota, n_aval, verificado = p["cliente_nota"], p["cliente_avaliacoes"], p["cliente_pagamento_verificado"]
    if nota is None and not n_aval and verificado is None:
        return round(peso * 0.4, 1), "sem dados do cliente (nota neutra)"

    pontos, partes = 0.0, []
    # Nota média (até 48% do peso)
    if nota is not None and (n_aval is None or n_aval > 0):
        pontos += 0.48 * _limitar(nota / 5)
        partes.append(f"nota {nota:.1f}/5")
    else:
        pontos += 0.16
        partes.append("sem avaliações")
    # Pagamento verificado (até 32%)
    if verificado:
        pontos += 0.32
        partes.append("pagamento verificado")
    elif verificado is None:
        pontos += 0.12
    else:
        partes.append("pagamento não verificado")
    # Quantidade de avaliações (até 20%)
    if n_aval:
        pontos += 0.20 * _limitar(n_aval / 10)
        partes.append(f"{n_aval} avaliações")
    return round(peso * pontos, 1), ", ".join(partes)


def nota_dificuldade(cfg: dict, av: AvaliacaoIA) -> tuple[float, str]:
    peso = cfg["pesos"]["dificuldade"]
    frac = (10 - av.dificuldade) / 9
    return round(peso * frac, 1), f"dificuldade real {av.dificuldade}/10, nível {av.nivel_estimado}"


def nota_remuneracao(cfg: dict, p: dict, valor_brl, av: AvaliacaoIA) -> tuple[float, str]:
    """Compara com a média da plataforma/categoria. Se não houver amostras suficientes,
    compara o valor por hora estimado com o valor-hora de referência do config."""
    peso = cfg["pesos"]["remuneracao"]
    if valor_brl is None:
        return round(peso * 0.3, 1), "sem orçamento para comparar"

    media, origem = media_mercado.media(cfg, p["plataforma"], p["categoria"], p["tipo"])
    if media:
        razao = valor_brl / media
        base = origem
    else:
        ref = cfg["orcamento"]["valor_hora_referencia_brl"]
        valor_hora = valor_brl if p["tipo"] == "hora" else valor_brl / av.horas_estimadas
        razao = valor_hora / ref
        base = f"R$ {valor_hora:,.0f}/h estimado vs referência R$ {ref}/h"
    # razão 0,5 -> 0 ponto; 1,0 -> metade; 1,5 ou mais -> peso cheio
    frac = _limitar(razao - 0.5)
    return round(peso * frac, 1), f"{razao:.2f}× ({base})"


def avaliar_partes(cfg: dict, p: dict, valor_brl, av: AvaliacaoIA) -> tuple[dict, dict]:
    valor_total = valor_brl * av.horas_estimadas if (valor_brl is not None and p["tipo"] == "hora") else valor_brl
    partes = {
        "orcamento": nota_orcamento(cfg, valor_total),
        "cliente": nota_cliente(cfg, p),
        "dificuldade": nota_dificuldade(cfg, av),
        "remuneracao": nota_remuneracao(cfg, p, valor_brl, av),
    }
    notas = {k: v[0] for k, v in partes.items()}
    detalhes = {k: v[1] for k, v in partes.items()}
    notas["total"] = round(sum(notas.values()), 1)
    detalhes["valor_total_brl"] = valor_total
    return notas, detalhes
