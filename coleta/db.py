"""Acesso ao Postgres (Neon, Supabase ou qualquer outro). Usa a variável DATABASE_URL."""
import os
from pathlib import Path

import psycopg


def conectar():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Defina a variável DATABASE_URL (string de conexão do Postgres).")
    conn = psycopg.connect(url, autocommit=True)
    conn.execute(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
    return conn


def registrar_ceasas(conn, coletores):
    with conn.cursor() as cur:
        cur.executemany(
            "insert into ceasa (id, nome, uf) values (%s, %s, %s) "
            "on conflict (id) do update set nome = excluded.nome, uf = excluded.uf",
            [(c.id, c.nome, c.uf) for c in coletores])


def datas_resolvidas(conn, cid, max_tentativas=3):
    """Datas que não precisam ser baixadas de novo (ok, ou falharam vezes demais)."""
    rows = conn.execute(
        "select data from boletim where ceasa_id = %s and (status = 'ok' or tentativas >= %s)",
        (cid, max_tentativas)).fetchall()
    return {r[0] for r in rows}


def gravar_boletim(conn, cid, data, status, sha=None, linhas=(), erro=None):
    with conn.transaction():
        conn.execute(
            """insert into boletim (ceasa_id, data, status, pdf_sha256, erro)
               values (%s, %s, %s, %s, %s)
               on conflict (ceasa_id, data) do update set
                 status = excluded.status, pdf_sha256 = excluded.pdf_sha256, erro = excluded.erro,
                 tentativas = boletim.tentativas + 1, normalizado = false, coletado_em = now()""",
            (cid, data, status, sha, erro))
        conn.execute("delete from linha_bruta where ceasa_id = %s and data = %s", (cid, data))
        if linhas:
            with conn.cursor() as cur:
                cur.executemany(
                    "insert into linha_bruta (ceasa_id, data, pagina, ordem, metodo, celulas) "
                    "values (%s, %s, %s, %s, %s, %s)",
                    [(cid, data, p, o, m, c) for p, o, m, c in linhas])


def pendentes_normalizacao(conn, cid):
    rows = conn.execute(
        "select data from boletim where ceasa_id = %s and status = 'ok' and not normalizado order by data",
        (cid,)).fetchall()
    return [r[0] for r in rows]


def linhas(conn, cid, data):
    return conn.execute(
        "select pagina, ordem, metodo, celulas from linha_bruta "
        "where ceasa_id = %s and data = %s order by pagina, ordem", (cid, data)).fetchall()


CAMPOS = ("produto", "detalhe", "embalagem", "minimo", "comum", "maximo", "situacao", "conferencia")


def gravar_cotacoes(conn, cid, data, cotacoes):
    with conn.transaction():
        conn.execute("delete from cotacao where ceasa_id = %s and data = %s", (cid, data))
        if cotacoes:
            with conn.cursor() as cur:
                cur.executemany(
                    f"insert into cotacao (ceasa_id, data, {', '.join(CAMPOS)}) "
                    f"values (%s, %s, {', '.join(['%s'] * len(CAMPOS))}) on conflict do nothing",
                    [(cid, data, *(c.get(k, "" if k == "detalhe" else "pendente" if k == "conferencia" else None)
                                   for k in CAMPOS)) for c in cotacoes])
        conn.execute("update boletim set normalizado = true where ceasa_id = %s and data = %s", (cid, data))
