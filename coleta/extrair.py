"""Extrai as linhas cruas de um PDF de boletim (sem interpretar colunas)."""
import io
import re

import pdfplumber


def linhas_do_pdf(pdf: bytes):
    """Retorna [(pagina, ordem, metodo, [celulas...])]. Tabelas quando o PDF tem; senão, texto."""
    out = []
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        for n, pg in enumerate(doc.pages, 1):
            k = 0
            tabelas = pg.extract_tables()
            if tabelas:
                for t in tabelas:
                    for row in t:
                        cel = [(c or "").replace("\n", " ").strip() for c in row]
                        if any(cel):
                            out.append((n, k, "tabela", cel))
                            k += 1
            else:
                for ln in (pg.extract_text() or "").splitlines():
                    if ln.strip():
                        out.append((n, k, "texto", re.split(r"\s{2,}", ln.strip())))
                        k += 1
    return out
