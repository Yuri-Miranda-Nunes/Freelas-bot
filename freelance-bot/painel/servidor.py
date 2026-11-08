"""Painel local: lista de projetos, notas, critérios e rascunhos. Envio é sempre manual.

Uso: python painel/servidor.py   (abre em http://127.0.0.1:5000)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, abort, redirect, render_template_string, request, url_for  # noqa: E402

from avaliacao import ia  # noqa: E402
from config import carregar_config, configurar_log  # noqa: E402
from dados import armazenamento as db  # noqa: E402
from redacao import portfolio, redator  # noqa: E402

configurar_log("painel")
app = Flask(__name__)

ROTULOS = {"novo": "Novos", "revisado": "Revisados", "enviado": "Enviados",
           "descartado": "Descartados", "reprovado": "Reprovados"}

BASE = """<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Freelance bot</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--tx:#1d2330;--mut:#667085;--bd:#e3e6eb;--ac:#2563eb;--ok:#15803d;--bad:#b42318;--warn:#b54708}
@media (prefers-color-scheme:dark){:root{--bg:#12151b;--card:#1b1f27;--tx:#e6e8ec;--mut:#98a2b3;--bd:#2c323d;--ac:#6ea8ff;--ok:#4ade80;--bad:#f97066;--warn:#fdb022}}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,Segoe UI,sans-serif;background:var(--bg);color:var(--tx)}
main{max-width:1100px;margin:0 auto;padding:16px}a{color:var(--ac);text-decoration:none}a:hover{text-decoration:underline}
header{display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin-bottom:16px}header h1{font-size:18px;margin:0 8px 0 0}
.tabs a{padding:6px 10px;border-radius:6px;border:1px solid var(--bd);background:var(--card);margin-right:4px;display:inline-block;margin-bottom:4px}
.tabs a.on{background:var(--ac);color:#fff;border-color:var(--ac)}
.card{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:16px;margin-bottom:16px}
table{width:100%;border-collapse:collapse}th,td{padding:8px;border-bottom:1px solid var(--bd);text-align:left;vertical-align:top}
th{color:var(--mut);font-weight:600;font-size:13px}.n{font-variant-numeric:tabular-nums;font-weight:700}
.mut{color:var(--mut);font-size:13px}.pill{font-size:12px;padding:2px 8px;border-radius:99px;border:1px solid var(--bd)}
.alta{color:var(--ok)}.media{color:var(--warn)}.baixa{color:var(--bad)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
.box{border:1px solid var(--bd);border-radius:8px;padding:10px}.box b{font-size:20px}
textarea{width:100%;min-height:260px;font:14px/1.5 system-ui,sans-serif;padding:10px;border:1px solid var(--bd);border-radius:8px;background:var(--bg);color:var(--tx)}
button,.btn{font:inherit;padding:7px 14px;border-radius:7px;border:1px solid var(--bd);background:var(--card);color:var(--tx);cursor:pointer;display:inline-block}
button.pri{background:var(--ac);border-color:var(--ac);color:#fff}button.perigo{color:var(--bad)}
.acoes{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}form{display:inline}
pre{white-space:pre-wrap;font:14px/1.5 system-ui,sans-serif;margin:0}
.scroll{overflow-x:auto}
</style></head><body><main>
<header><h1><a href="/">Freelance bot</a></h1>
<nav class="tabs">{% for s,r in rotulos.items() %}<a href="/?status={{s}}" class="{{'on' if status==s}}">{{r}} ({{contagem.get(s,0)}})</a>{% endfor %}
<a href="/rodadas" class="{{'on' if status=='rodadas'}}">Rodadas</a></nav></header>
{% block conteudo %}{% endblock %}</main></body></html>"""

LISTA = BASE.replace("{% block conteudo %}{% endblock %}", """
<div class="card scroll">{% if not projetos %}<p class="mut">Nenhum projeto aqui.</p>{% else %}
<table><tr><th>Nota</th><th>Projeto</th><th>Plataforma</th><th>Orçamento</th><th>Nível</th><th>Coletado</th></tr>
{% for p in projetos %}<tr>
<td class="n {{classe(p['nota_total'])}}">{{ '%.0f'|format(p['nota_total']) if p['nota_total'] is not none else '–' }}</td>
<td><a href="/projeto/{{p['id']}}">{{p['titulo']}}</a><div class="mut">{{p['categoria']}}</div></td>
<td>{{p['plataforma']}}</td><td>{{orc(p)}}</td><td>{{p['nivel_declarado'] or '–'}}</td>
<td class="mut">{{p['coletado_em'][:16].replace('T',' ')}}</td></tr>{% endfor %}</table>{% endif %}</div>""")

DETALHE = BASE.replace("{% block conteudo %}{% endblock %}", """
<div class="card"><h2 style="margin-top:0">{{p['titulo']}}</h2>
<p class="mut">{{p['plataforma']}} · {{p['categoria']}} · status <span class="pill">{{p['status']}}</span>
 · publicado {{p['publicado'] or '?'}} · propostas {{p['propostas'] if p['propostas'] is not none else '?'}}</p>
<p><a href="{{p['url']}}" target="_blank" rel="noopener">Abrir na plataforma ↗</a></p>
<div class="grid">
<div class="box"><div class="mut">Nota total</div><b class="{{classe(p['nota_total'])}}">{{ '%.1f'|format(p['nota_total']) if p['nota_total'] is not none else '–' }}</b></div>
{% for k,r in [('orcamento','Orçamento'),('cliente','Cliente'),('dificuldade','Dificuldade'),('remuneracao','Remuneração vs média')] %}
<div class="box"><div class="mut">{{r}} (máx. {{pesos[k]}})</div><b>{{ '%.1f'|format(p['nota_'+k]) if p['nota_'+k] is not none else '–' }}</b>
<div class="mut">{{crit.get(k,'')}}</div></div>{% endfor %}</div>
{% if motivos %}<p><b>Motivos da reprovação:</b></p><ul>{% for m in motivos %}<li>{{m}}</li>{% endfor %}</ul>{% endif %}
{% if p['erro'] %}<p class="baixa">Último erro: {{p['erro']}}</p>{% endif %}
</div>
{% if av %}<div class="card"><h3 style="margin-top:0">Análise da IA</h3>
<p>{{av.get('resumo','')}}</p>
<p class="mut">Nível estimado: <b>{{av.get('nivel_estimado')}}</b> · dificuldade <b>{{av.get('dificuldade')}}/10</b>
 · ≈ <b>{{av.get('horas_estimadas')}}</b> h · compatibilidade com portfólio <b>{{av.get('compatibilidade_portfolio')}}/10</b>
 {% if av.get('suspeito') %}· <span class="baixa">suspeito</span>{% endif %}
 {% if av.get('modelo_usado') %}<br>Modelo: {{av['modelo_usado']}}{% endif %}</p>
<p>{{av.get('justificativa','')}}</p>
{% if av.get('alertas') %}<p><b>Alertas:</b></p><ul>{% for a in av['alertas'] %}<li>{{a}}</li>{% endfor %}</ul>{% endif %}
</div>{% endif %}
<div class="card"><h3 style="margin-top:0">Rascunho da proposta</h3>
{% if p['rascunho'] %}
<form method="post" action="/projeto/{{p['id']}}/rascunho" style="display:block">
<textarea name="texto" id="rasc">{{p['rascunho']}}</textarea>
<div class="acoes"><button class="pri" type="submit">Salvar edição</button>
<button type="button" onclick="navigator.clipboard.writeText(document.getElementById('rasc').value);this.textContent='Copiado'">Copiar</button></div></form>
{% else %}<p class="mut">Sem rascunho.</p>
{% if av %}<form method="post" action="/projeto/{{p['id']}}/gerar"><button>Gerar rascunho mesmo assim</button></form>{% endif %}
{% endif %}
<div class="acoes">
{% for s,r in [('enviado','Marcar como enviado'),('revisado','Marcar como revisado'),('descartado','Descartar')] if s != p['status'] %}
<form method="post" action="/projeto/{{p['id']}}/status"><input type="hidden" name="status" value="{{s}}">
<button class="{{'perigo' if s=='descartado' else ''}}">{{r}}</button></form>{% endfor %}
</div></div>
<div class="card"><h3 style="margin-top:0">Descrição</h3><pre>{{p['descricao']}}</pre>
<p class="mut">Habilidades: {{hab|join(', ')}}</p></div>""")

RODADAS = BASE.replace("{% block conteudo %}{% endblock %}", """
<div class="card scroll"><table><tr><th>Início</th><th>Fim</th><th>Resumo</th></tr>
{% for r in rodadas %}<tr><td>{{r['inicio'][:16].replace('T',' ')}}</td><td>{{(r['fim'] or '')[:16].replace('T',' ')}}</td><td>{{r['resumo']}}</td></tr>{% endfor %}
</table></div>""")


def _classe(n):
    if n is None:
        return ""
    return "alta" if n >= 70 else "media" if n >= 50 else "baixa"


def _orc(p):
    if p["orcamento_min"] is None and p["orcamento_max"] is None:
        return "–"
    faixa = " – ".join(f"{v:,.0f}" for v in (p["orcamento_min"], p["orcamento_max"]) if v is not None)
    return f"{p['moeda']} {faixa}{'/h' if p['tipo'] == 'hora' else ''}"


def _ctx(**kw):
    return dict(rotulos=ROTULOS, contagem=db.contagem_status(), classe=_classe, orc=_orc, **kw)


@app.route("/")
def inicio():
    status = request.args.get("status", "novo")
    plataforma = request.args.get("plataforma")
    return render_template_string(LISTA, **_ctx(status=status,
                                  projetos=db.listar(status, plataforma)))


@app.route("/projeto/<int:pid>")
def detalhe(pid):
    p = db.obter(pid)
    if not p:
        abort(404)
    if p["status"] == "novo":           # abrir no painel = revisado
        db.mudar_status(pid, "revisado")
        p = db.obter(pid)
    av = json.loads(p["avaliacao_ia"]) if p["avaliacao_ia"] else None
    return render_template_string(DETALHE, **_ctx(
        status=p["status"], p=p, av=av,
        crit=(av or {}).get("criterios", {}),
        motivos=json.loads(p["motivos"] or "[]"),
        hab=json.loads(p["habilidades"] or "[]"),
        pesos=carregar_config()["pesos"]))


@app.post("/projeto/<int:pid>/status")
def status(pid):
    novo = request.form.get("status")
    if novo not in ("revisado", "enviado", "descartado"):
        abort(400)
    db.mudar_status(pid, novo)
    return redirect(url_for("detalhe", pid=pid))


@app.post("/projeto/<int:pid>/rascunho")
def rascunho(pid):
    db.salvar_rascunho(pid, request.form.get("texto", ""))
    return redirect(url_for("detalhe", pid=pid))


@app.post("/projeto/<int:pid>/gerar")
def gerar(pid):
    p = db.obter(pid)
    if not p or not p["avaliacao_ia"]:
        abort(404)
    d = dict(p)
    d["habilidades"] = json.loads(d["habilidades"] or "[]")
    dados_av = json.loads(p["avaliacao_ia"])
    dados_av.pop("criterios", None)
    dados_av.pop("modelo_usado", None)
    try:
        texto = redator.gerar_rascunho(carregar_config(), d, ia.AvaliacaoIA(**dados_av), portfolio.carregar())
        db.salvar_rascunho(pid, texto)
    except ia.ErroIA as e:
        db.registrar_erro(pid, str(e))
    return redirect(url_for("detalhe", pid=pid))


@app.route("/rodadas")
def rodadas():
    return render_template_string(RODADAS, **_ctx(status="rodadas", rodadas=db.ultimas_rodadas(30)))


if __name__ == "__main__":
    cfg = carregar_config()
    db.iniciar()
    app.run(host=cfg["painel"]["host"], port=cfg["painel"]["porta"], debug=False)
