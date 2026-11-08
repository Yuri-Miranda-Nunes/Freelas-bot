"""Chamadas de IA: avaliação estruturada e redação de propostas.

Dois provedores, escolhidos em config.json -> ia.provedor:
  "anthropic"      API do Claude (SDK oficial, saída estruturada garantida)
  "openai_compat"  qualquer endpoint no padrão OpenAI, como o FreeLLMAPI local
                   (http://localhost:3001/v1). A resposta é validada e, se vier
                   fora do formato, o pedido é repetido.
"""
import json
import logging
import re
import unicodedata
from typing import Literal

import anthropic
import requests
from pydantic import BaseModel, ValidationError

from config import carregar_segredos

log = logging.getLogger("ia")

# Modelo que respondeu a última chamada (o FreeLLMAPI alterna entre vários).
ultimo_modelo = ""


class ErroIA(Exception):
    pass


class AvaliacaoIA(BaseModel):
    nivel_estimado: Literal["iniciante", "intermediario", "avancado"]
    dificuldade: int                 # 1 (trivial) a 10 (muito difícil)
    horas_estimadas: float           # horas de trabalho para entregar o escopo descrito
    compatibilidade_portfolio: int   # 0 a 10
    suspeito: bool                   # golpe, pedido antiético, escopo ilegal, pagamento fora da plataforma
    alertas: list[str]
    habilidades_necessarias: list[str]
    resumo: str                      # 1-2 frases do que o cliente quer
    justificativa: str               # por que essa dificuldade e essas horas


# ======================================================================
# Prompts (compartilhados pelos dois provedores)
# ======================================================================

SISTEMA_AVALIACAO = """Você avalia projetos publicados em plataformas de freelance para um desenvolvedor \
específico, cujo portfólio está abaixo. Seja realista e conservador: o objetivo é que ele só gaste \
tempo com projetos que consegue entregar bem.

Como preencher:
- nivel_estimado: o nível de experiência que o projeto realmente exige, pelo escopo técnico \
(não pelo que o cliente declarou).
- dificuldade: 1 a 10, considerando o escopo real, ambiguidades, integrações e riscos. \
Use 1-3 para tarefas pequenas e bem definidas, 4-6 para sistemas pequenos ou integrações comuns, \
7-8 para sistemas com várias partes ou tecnologia que ele não domina, 9-10 para algo que exige especialista.
- horas_estimadas: horas de trabalho efetivo para este desenvolvedor entregar o escopo descrito, \
incluindo testes e comunicação. Se o escopo for vago, estime o mínimo razoável e diga isso nos alertas.
- compatibilidade_portfolio: 0 a 10, quanto o portfólio dele comprova as habilidades necessárias.
- suspeito: true para golpes (pedir pagamento antecipado, contato fora da plataforma logo de início, \
"teste grátis" grande), fraudes, contas falsas, burlar sistemas, apostas/cassino, ou algo ilegal.
- alertas: riscos concretos (escopo vago, prazo irreal, orçamento incompatível, etc.). Lista vazia se não houver.
- resumo e justificativa: em português, curtos e objetivos.

PORTFÓLIO DO DESENVOLVEDOR:
"""

INSTRUCAO_JSON = """

FORMATO DA RESPOSTA: responda somente com um objeto JSON válido, sem texto antes ou depois e sem \
blocos de código, com exatamente estas chaves:
{
  "nivel_estimado": "iniciante" | "intermediario" | "avancado",
  "dificuldade": inteiro de 1 a 10,
  "horas_estimadas": número,
  "compatibilidade_portfolio": inteiro de 0 a 10,
  "suspeito": true | false,
  "alertas": [lista de textos],
  "habilidades_necessarias": [lista de textos],
  "resumo": "texto",
  "justificativa": "texto"
}"""

SISTEMA_REDACAO = """Você escreve rascunhos de propostas para projetos freelance em nome do \
desenvolvedor cujo portfólio está abaixo. O desenvolvedor vai revisar e enviar manualmente.

Regras:
- Escreva no idioma indicado no pedido.
- Comece pelo problema do cliente, não por "Olá, meu nome é". Mostre que leu o projeto.
- Cite só evidências reais do portfólio (projetos, repositórios, experiências) que tenham relação \
direta com o pedido. Nunca invente experiência, números, clientes ou links.
- Descreva em 3 a 5 passos curtos como faria o trabalho.
- Termine com 1 ou 2 perguntas objetivas que esclareçam o escopo.
- Entre 120 e 250 palavras. Tom profissional e direto, sem exageros nem clichês.
- Não proponha valor nem prazo; o desenvolvedor define isso.
- Responda só com o texto da proposta, sem título nem comentários.

PORTFÓLIO DO DESENVOLVEDOR:
"""

IDIOMAS = {"pt": "português do Brasil", "en": "inglês", "es": "espanhol"}


def _pedido_avaliacao(projeto: dict, orcamento_txt: str) -> str:
    return (
        f"Plataforma: {projeto['plataforma']}\n"
        f"Título: {projeto['titulo']}\n"
        f"Categoria: {projeto['categoria']}\n"
        f"Habilidades listadas: {', '.join(projeto['habilidades'])}\n"
        f"Nível declarado pelo cliente: {projeto['nivel_declarado'] or 'não informado'}\n"
        f"Tipo: {'por hora' if projeto['tipo'] == 'hora' else 'preço fixo'}\n"
        f"Orçamento: {orcamento_txt}\n"
        f"Propostas já enviadas: {projeto['propostas'] if projeto['propostas'] is not None else 'desconhecido'}\n\n"
        f"Descrição:\n{projeto['descricao'][:12000]}"
    )


def _pedido_redacao(projeto: dict, avaliacao: AvaliacaoIA) -> str:
    return (
        f"Idioma da proposta: {IDIOMAS.get(projeto['idioma'], 'inglês')}\n"
        f"Plataforma: {projeto['plataforma']}\n"
        f"Título: {projeto['titulo']}\n"
        f"Habilidades listadas: {', '.join(projeto['habilidades'])}\n"
        f"Resumo da análise: {avaliacao.resumo}\n"
        f"Riscos identificados: {'; '.join(avaliacao.alertas) or 'nenhum'}\n\n"
        f"Descrição do projeto:\n{projeto['descricao'][:12000]}"
    )


def _ajustar(av: AvaliacaoIA) -> AvaliacaoIA:
    av.dificuldade = max(1, min(10, av.dificuldade))
    av.compatibilidade_portfolio = max(0, min(10, av.compatibilidade_portfolio))
    av.horas_estimadas = max(0.5, av.horas_estimadas)
    return av


# ======================================================================
# Interface usada pelo resto do app
# ======================================================================

def provedor(cfg: dict) -> str:
    return cfg["ia"].get("provedor", "anthropic")


def avaliar(cfg: dict, projeto: dict, portfolio: str, orcamento_txt: str) -> AvaliacaoIA:
    if provedor(cfg) == "openai_compat":
        return _ajustar(_compat_avaliar(cfg, projeto, portfolio, orcamento_txt))
    return _ajustar(_claude_avaliar(cfg, projeto, portfolio, orcamento_txt))


def redigir(cfg: dict, projeto: dict, avaliacao: AvaliacaoIA, portfolio: str) -> str:
    if provedor(cfg) == "openai_compat":
        return _compat_redigir(cfg, projeto, avaliacao, portfolio)
    return _claude_redigir(cfg, projeto, avaliacao, portfolio)


# ======================================================================
# Provedor "anthropic" (Claude)
# ======================================================================

# Se o modelo principal recusar uma requisição, a API refaz automaticamente em outro modelo.
_BETAS = ["server-side-fallback-2026-07-01"]
_cliente = None


def _cliente_claude() -> anthropic.Anthropic:
    global _cliente
    if _cliente is None:
        chave = carregar_segredos().get("anthropic_api_key")
        if not chave or chave.startswith("sk-ant-..."):
            raise ErroIA("Chave da API do Claude não configurada (config/segredos.json ou ANTHROPIC_API_KEY).")
        _cliente = anthropic.Anthropic(api_key=chave, max_retries=4)
    return _cliente


def _claude_chamar(**kw):
    global ultimo_modelo
    try:
        if "output_format" in kw:
            resp = _cliente_claude().beta.messages.parse(betas=_BETAS, fallbacks="default", **kw)
        else:
            resp = _cliente_claude().beta.messages.create(betas=_BETAS, fallbacks="default", **kw)
    except anthropic.AuthenticationError as e:
        raise ErroIA("Chave da API do Claude inválida.") from e
    except anthropic.BadRequestError as e:
        raise ErroIA(f"Requisição rejeitada pela API: {e.message}") from e
    except anthropic.RateLimitError as e:
        raise ErroIA("Limite de uso da API atingido; tenta de novo na próxima rodada.") from e
    except anthropic.APIStatusError as e:
        raise ErroIA(f"Erro da API ({e.status_code}): {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise ErroIA("Sem conexão com a API do Claude.") from e
    ultimo_modelo = resp.model
    if resp.stop_reason == "refusal":
        raise ErroIA("A IA recusou o pedido.")
    return resp


def _claude_avaliar(cfg, projeto, portfolio, orcamento_txt) -> AvaliacaoIA:
    resp = _claude_chamar(
        model=cfg["ia"]["modelo"],
        max_tokens=16000,
        output_config={"effort": cfg["ia"]["effort_avaliacao"]},
        system=[{"type": "text", "text": SISTEMA_AVALIACAO + portfolio,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": _pedido_avaliacao(projeto, orcamento_txt)}],
        output_format=AvaliacaoIA,
    )
    if resp.parsed_output is None:
        raise ErroIA(f"Resposta da IA sem avaliação (stop_reason={resp.stop_reason}).")
    return resp.parsed_output


def _claude_redigir(cfg, projeto, avaliacao, portfolio) -> str:
    resp = _claude_chamar(
        model=cfg["ia"]["modelo"],
        max_tokens=16000,
        output_config={"effort": cfg["ia"]["effort_redacao"]},
        system=[{"type": "text", "text": SISTEMA_REDACAO + portfolio,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": _pedido_redacao(projeto, avaliacao)}],
    )
    texto = "".join(b.text for b in resp.content if b.type == "text").strip()
    if not texto:
        raise ErroIA(f"Rascunho vazio (stop_reason={resp.stop_reason}).")
    return texto


# ======================================================================
# Provedor "openai_compat" (FreeLLMAPI ou outro endpoint no padrão OpenAI)
# ======================================================================

_sem_json_mode = False   # vira True se o endpoint rejeitar response_format


def _compat_chamar(cfg: dict, mensagens: list[dict], json_mode: bool) -> str:
    global ultimo_modelo, _sem_json_mode
    conf = cfg["ia"]["openai_compat"]
    chave = carregar_segredos().get("openai_compat_api_key", "")
    if not chave or chave.startswith("freellmapi-..."):
        raise ErroIA("Chave do FreeLLMAPI não configurada (openai_compat_api_key em config/segredos.json).")

    corpo = {"model": conf.get("modelo", "auto"), "messages": mensagens}
    if conf.get("temperatura") is not None:
        corpo["temperature"] = conf["temperatura"]
    if json_mode and not _sem_json_mode:
        corpo["response_format"] = {"type": "json_object"}

    url = conf["base_url"].rstrip("/") + "/chat/completions"
    try:
        r = requests.post(url, json=corpo, timeout=conf.get("timeout_seg", 180),
                          headers={"Authorization": f"Bearer {chave}"})
    except requests.ConnectionError as e:
        raise ErroIA(f"Sem conexão com {conf['base_url']} (o FreeLLMAPI está rodando?).") from e
    except requests.Timeout as e:
        raise ErroIA("Tempo esgotado esperando o FreeLLMAPI.") from e

    if r.status_code == 400 and "response_format" in corpo:
        log.warning("Endpoint rejeitou response_format; seguindo só com a instrução no prompt.")
        _sem_json_mode = True
        return _compat_chamar(cfg, mensagens, json_mode)
    if r.status_code in (401, 403):
        raise ErroIA("Chave do FreeLLMAPI inválida (copie a chave da página Keys do painel dele).")
    if r.status_code == 429:
        raise ErroIA("Limite de uso atingido em todos os provedores gratuitos; tenta de novo na próxima rodada.")
    if r.status_code >= 400:
        raise ErroIA(f"Erro do FreeLLMAPI ({r.status_code}): {r.text[:300]}")

    try:
        dados = r.json()
        ultimo_modelo = dados.get("model", "")
        texto = dados["choices"][0]["message"].get("content") or ""
    except (ValueError, KeyError, IndexError) as e:
        raise ErroIA(f"Resposta inesperada do FreeLLMAPI: {r.text[:300]}") from e
    # Alguns modelos de raciocínio devolvem o pensamento entre <think> ... </think>
    return re.sub(r"<think>.*?</think>", "", texto, flags=re.S).strip()


def _sem_acento(t: str) -> str:
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower().strip()


def _extrair_json(texto: str) -> dict:
    texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto.strip())
    inicio, fim = texto.find("{"), texto.rfind("}")
    if inicio < 0 or fim <= inicio:
        raise ValueError("nenhum objeto JSON na resposta")
    dados = json.loads(texto[inicio:fim + 1])
    # Tolerâncias comuns em modelos menores
    if isinstance(dados.get("nivel_estimado"), str):
        dados["nivel_estimado"] = _sem_acento(dados["nivel_estimado"])
    for chave in ("alertas", "habilidades_necessarias"):
        if dados.get(chave) is None:
            dados[chave] = []
        elif isinstance(dados[chave], str):
            dados[chave] = [dados[chave]] if dados[chave] else []
    for chave in ("dificuldade", "compatibilidade_portfolio"):
        if isinstance(dados.get(chave), (float, str)):
            dados[chave] = round(float(dados[chave]))
    return dados


def _compat_avaliar(cfg, projeto, portfolio, orcamento_txt) -> AvaliacaoIA:
    mensagens = [
        {"role": "system", "content": SISTEMA_AVALIACAO + portfolio + INSTRUCAO_JSON},
        {"role": "user", "content": _pedido_avaliacao(projeto, orcamento_txt)},
    ]
    tentativas = cfg["ia"]["openai_compat"].get("tentativas_json", 3)
    erro = ""
    for n in range(1, tentativas + 1):
        texto = _compat_chamar(cfg, mensagens, json_mode=True)
        try:
            return AvaliacaoIA.model_validate(_extrair_json(texto))
        except (ValueError, ValidationError) as e:
            erro = str(e).splitlines()[0]
            log.warning("Resposta fora do formato (tentativa %d/%d, modelo %s): %s",
                        n, tentativas, ultimo_modelo or "?", erro)
            mensagens = mensagens[:2] + [
                {"role": "assistant", "content": texto[:4000]},
                {"role": "user", "content": f"A resposta não é um JSON válido no formato pedido ({erro}). "
                                            "Responda de novo só com o objeto JSON, com todas as chaves."},
            ]
    raise ErroIA(f"IA não devolveu uma avaliação válida após {tentativas} tentativas: {erro}")


def _compat_redigir(cfg, projeto, avaliacao, portfolio) -> str:
    texto = _compat_chamar(cfg, [
        {"role": "system", "content": SISTEMA_REDACAO + portfolio},
        {"role": "user", "content": _pedido_redacao(projeto, avaliacao)},
    ], json_mode=False)
    if not texto:
        raise ErroIA("Rascunho vazio.")
    return texto
