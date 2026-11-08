"""Soma as partes e aplica as regras de aprovação."""
from .ia import AvaliacaoIA


def decidir(cfg: dict, p: dict, notas: dict, detalhes: dict, av: AvaliacaoIA) -> tuple[bool, list[str]]:
    ap = cfg["aprovacao"]
    reprovacoes = []

    if notas["total"] < ap["nota_minima"]:
        reprovacoes.append(f"nota {notas['total']} abaixo de {ap['nota_minima']}")
    if av.suspeito:
        reprovacoes.append("IA marcou como suspeito: " + ("; ".join(av.alertas) or "sem detalhe"))
    if av.nivel_estimado == "avancado":
        reprovacoes.append("IA estima que o projeto exige nível avançado")
    if av.dificuldade > ap["dificuldade_maxima"]:
        reprovacoes.append(f"dificuldade {av.dificuldade} acima do máximo {ap['dificuldade_maxima']}")

    intermediario = p["nivel_declarado"] == "intermediario" or av.nivel_estimado == "intermediario"
    if intermediario:
        regra = ap["intermediario"]
        if av.dificuldade > regra["dificuldade_maxima"]:
            reprovacoes.append(f"intermediário com dificuldade {av.dificuldade} "
                               f"(máx. {regra['dificuldade_maxima']})")
        valor = detalhes.get("valor_total_brl")
        if valor is not None and valor < regra["orcamento_minimo_brl"]:
            reprovacoes.append(f"intermediário com orçamento ≈ R$ {valor:,.0f} "
                               f"(mín. R$ {regra['orcamento_minimo_brl']})")

    return not reprovacoes, reprovacoes
