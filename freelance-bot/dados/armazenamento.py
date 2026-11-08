"""Banco SQLite: projetos, notas, critérios, rascunhos, status, amostras de mercado e câmbio."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from config import CAMINHO_BANCO, PASTA_DADOS

STATUS_VALIDOS = ("pendente", "novo", "reprovado", "revisado", "enviado", "descartado")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS projetos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plataforma TEXT NOT NULL,
    id_externo TEXT NOT NULL,
    url TEXT, titulo TEXT, descricao TEXT, categoria TEXT, habilidades TEXT,
    nivel_declarado TEXT, tipo TEXT,
    orcamento_min REAL, orcamento_max REAL, moeda TEXT, orcamento_brl REAL,
    cliente_nota REAL, cliente_avaliacoes INTEGER, cliente_pagamento_verificado INTEGER,
    propostas INTEGER, publicado TEXT, idioma TEXT,
    status TEXT NOT NULL DEFAULT 'pendente',
    nota_total REAL, nota_orcamento REAL, nota_cliente REAL,
    nota_dificuldade REAL, nota_remuneracao REAL,
    avaliacao_ia TEXT, motivos TEXT, rascunho TEXT, erro TEXT,
    tentativas INTEGER NOT NULL DEFAULT 0,
    coletado_em TEXT, atualizado_em TEXT,
    UNIQUE (plataforma, id_externo)
);
CREATE INDEX IF NOT EXISTS ix_projetos_status ON projetos(status);

CREATE TABLE IF NOT EXISTS amostras (
    plataforma TEXT NOT NULL, id_externo TEXT NOT NULL,
    categoria TEXT, tipo TEXT, orcamento_brl REAL, coletado_em TEXT,
    UNIQUE (plataforma, id_externo)
);

CREATE TABLE IF NOT EXISTS cambio (
    data TEXT NOT NULL, moeda TEXT NOT NULL, valor REAL NOT NULL,
    UNIQUE (data, moeda)
);

CREATE TABLE IF NOT EXISTS rodadas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inicio TEXT, fim TEXT, coletados INTEGER, novos INTEGER,
    avaliados INTEGER, aprovados INTEGER, resumo TEXT
);
"""


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def conectar():
    PASTA_DADOS.mkdir(exist_ok=True)
    con = sqlite3.connect(CAMINHO_BANCO, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def iniciar():
    with conectar() as con:
        con.executescript(ESQUEMA)


# ---------- projetos ----------

def ja_visto(plataforma: str, id_externo: str) -> bool:
    with conectar() as con:
        return con.execute("SELECT 1 FROM projetos WHERE plataforma=? AND id_externo=?",
                           (plataforma, id_externo)).fetchone() is not None


def inserir_projeto(p: dict, orcamento_brl) -> int:
    with conectar() as con:
        cur = con.execute(
            """INSERT INTO projetos (plataforma, id_externo, url, titulo, descricao, categoria,
               habilidades, nivel_declarado, tipo, orcamento_min, orcamento_max, moeda, orcamento_brl,
               cliente_nota, cliente_avaliacoes, cliente_pagamento_verificado, propostas, publicado,
               idioma, status, coletado_em, atualizado_em)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pendente',?,?)""",
            (p["plataforma"], p["id_externo"], p["url"], p["titulo"], p["descricao"], p["categoria"],
             json.dumps(p["habilidades"], ensure_ascii=False), p["nivel_declarado"], p["tipo"],
             p["orcamento_min"], p["orcamento_max"], p["moeda"], orcamento_brl,
             p["cliente_nota"], p["cliente_avaliacoes"],
             None if p["cliente_pagamento_verificado"] is None else int(p["cliente_pagamento_verificado"]),
             p["propostas"], p["publicado"], p["idioma"], agora(), agora()))
        return cur.lastrowid


def pendentes(limite: int, max_tentativas: int = 3) -> list[sqlite3.Row]:
    with conectar() as con:
        return con.execute("SELECT * FROM projetos WHERE status='pendente' AND tentativas < ? "
                           "ORDER BY id LIMIT ?", (max_tentativas, limite)).fetchall()


def salvar_avaliacao(pid: int, status: str, notas: dict, avaliacao_ia: dict | None,
                     motivos: list[str], rascunho: str | None):
    with conectar() as con:
        con.execute(
            """UPDATE projetos SET status=?, nota_total=?, nota_orcamento=?, nota_cliente=?,
               nota_dificuldade=?, nota_remuneracao=?, avaliacao_ia=?, motivos=?, rascunho=?,
               erro=NULL, atualizado_em=? WHERE id=?""",
            (status, notas.get("total"), notas.get("orcamento"), notas.get("cliente"),
             notas.get("dificuldade"), notas.get("remuneracao"),
             json.dumps(avaliacao_ia, ensure_ascii=False) if avaliacao_ia else None,
             json.dumps(motivos, ensure_ascii=False), rascunho, agora(), pid))


def registrar_erro(pid: int, erro: str):
    with conectar() as con:
        con.execute("UPDATE projetos SET erro=?, tentativas=tentativas+1, atualizado_em=? WHERE id=?",
                    (erro[:1000], agora(), pid))


def mudar_status(pid: int, status: str):
    if status not in STATUS_VALIDOS:
        raise ValueError(status)
    with conectar() as con:
        con.execute("UPDATE projetos SET status=?, atualizado_em=? WHERE id=?", (status, agora(), pid))


def salvar_rascunho(pid: int, texto: str):
    with conectar() as con:
        con.execute("UPDATE projetos SET rascunho=?, atualizado_em=? WHERE id=?", (texto, agora(), pid))


def obter(pid: int):
    with conectar() as con:
        return con.execute("SELECT * FROM projetos WHERE id=?", (pid,)).fetchone()


def listar(status: str | None = None, plataforma: str | None = None, limite: int = 300):
    sql, args = "SELECT * FROM projetos WHERE status != 'pendente'", []
    if status:
        sql += " AND status=?"
        args.append(status)
    if plataforma:
        sql += " AND plataforma=?"
        args.append(plataforma)
    sql += " ORDER BY coletado_em DESC, nota_total DESC LIMIT ?"
    args.append(limite)
    with conectar() as con:
        return con.execute(sql, args).fetchall()


def contagem_status() -> dict:
    with conectar() as con:
        return {r["status"]: r["n"] for r in
                con.execute("SELECT status, COUNT(*) n FROM projetos GROUP BY status")}


# ---------- amostras de mercado ----------

def registrar_amostra(plataforma, id_externo, categoria, tipo, orcamento_brl):
    if orcamento_brl is None:
        return
    with conectar() as con:
        con.execute("INSERT OR IGNORE INTO amostras VALUES (?,?,?,?,?,?)",
                    (plataforma, id_externo, categoria, tipo, orcamento_brl, agora()))


def media_amostras(plataforma, categoria, tipo, desde: str):
    """Devolve (média, quantidade) para plataforma+categoria+tipo; categoria None = todas."""
    sql = ("SELECT AVG(orcamento_brl) m, COUNT(*) n FROM amostras "
           "WHERE plataforma=? AND tipo=? AND coletado_em >= ?")
    args = [plataforma, tipo, desde]
    if categoria is not None:
        sql += " AND categoria=?"
        args.append(categoria)
    with conectar() as con:
        r = con.execute(sql, args).fetchone()
        return r["m"], r["n"]


# ---------- câmbio ----------

def cambio_do_dia(data: str) -> dict:
    with conectar() as con:
        return {r["moeda"]: r["valor"] for r in
                con.execute("SELECT moeda, valor FROM cambio WHERE data=?", (data,))}


def salvar_cambio(data: str, valores: dict):
    with conectar() as con:
        con.executemany("INSERT OR REPLACE INTO cambio VALUES (?,?,?)",
                        [(data, m, v) for m, v in valores.items()])


# ---------- rodadas ----------

def registrar_rodada(inicio, fim, coletados, novos, avaliados, aprovados, resumo):
    with conectar() as con:
        con.execute("INSERT INTO rodadas (inicio, fim, coletados, novos, avaliados, aprovados, resumo) "
                    "VALUES (?,?,?,?,?,?,?)", (inicio, fim, coletados, novos, avaliados, aprovados, resumo))


def ultimas_rodadas(n=10):
    with conectar() as con:
        return con.execute("SELECT * FROM rodadas ORDER BY id DESC LIMIT ?", (n,)).fetchall()
