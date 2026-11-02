"""Lê as cotações validadas do banco e gera o dados.json do app."""
import pandas as pd

from .gerar_dados import gerar

SQL = """
select data as "Data", ceasa_id as "Mercado", produto as "Produto", detalhe as "Detalhe",
       embalagem as "Embalagem", minimo::float8 as "Min", comum::float8 as "Com",
       maximo::float8 as "Max", situacao as "Sit", conferencia as "Conferência"
from cotacao
where conferencia = 'validado' and data >= current_date - %s::int
"""


def exportar(conn, saida, dias=180):
    """dias: janela de histórico enviada ao app (mantém o JSON leve com muitas CEASAs)."""
    rotulos = dict(conn.execute("select id, nome from ceasa where ativo order by id").fetchall())
    cur = conn.execute(SQL, (dias,))
    df = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
    if df.empty:
        print("Nenhuma cotação validada no banco ainda: dados.json mantido.")
        return False
    df = df[df["Mercado"].isin(rotulos)]
    return gerar(df, saida, rotulos)
