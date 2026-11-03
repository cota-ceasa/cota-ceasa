"""CEASA-ES (Ceasa Grande Vitória) — formulário Scriptcase que gera o boletim em PDF.

Formulário: select #id_sc_field_mercado (Grande Vitória = 211) e #id_sc_field_datas, botão Ok.
Ao escolher o mercado (e às vezes a data) o site RECARREGA a página; por isso cada leitura
espera a página assentar e tolera o "Execution context was destroyed" da recarga.
Se o site mudar, rode:  python -m coleta.run --discover ES
"""
import re
from pathlib import Path
from urllib.parse import urljoin

from ..padronizar import cotacao, numero
from .base import Coletor, parse_data

URL = "http://200.198.51.71/detec/filtro_boletim_es/filtro_boletim_es.php"
SEL_MERCADO = "#id_sc_field_mercado"
SEL_DATAS = "#id_sc_field_datas"
MERCADO_ID = "211"  # CEASA GRANDE VITÓRIA
# grafias do boletim do ES que diferem do nome padrão (o resto casa sozinho)
APELIDOS = {}
LINHA = re.compile(r"^(.+?)\s+(CX \d+ DZ|ENG \d+ UNID|UN \d+,\d+ KG|UN|KG)\s+"
                   r"([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)(?:\s+(M[A-Z]{1,2}))?$")
BTN_OK = ["#sc_b_ok_t", "#sc_b_ok_b", "a:has-text('Ok')", "text=Ok"]


class ColetorES(Coletor):
    id = "ES"
    nome = "CEASA - Vitória (ES)"
    uf = "ES"

    @staticmethod
    def _contar(page, seletor, tentativas=60, minimo=2):
        """Espera o select ter ao menos 'minimo' opções, atravessando recargas da página."""
        for _ in range(tentativas):
            try:
                page.wait_for_load_state("domcontentloaded")
                if page.locator(f"{seletor} option").count() >= minimo:
                    return True
            except Exception:  # noqa: BLE001 (página recarregando no meio da leitura)
                pass
            page.wait_for_timeout(500)
        return False

    def _abrir(self, page):
        page.goto(URL, wait_until="networkidle", timeout=60000)
        if not self._contar(page, SEL_MERCADO):
            raise RuntimeError("formulário mudou: select de mercado não encontrado (rode --discover ES)")
        valor = MERCADO_ID
        for o in page.locator(f"{SEL_MERCADO} option").all():  # confirma pelo nome, se o código mudar
            if "GRANDE VIT" in o.inner_text().upper():
                valor = o.get_attribute("value")
        page.select_option(SEL_MERCADO, value=valor)   # dispara a recarga
        page.wait_for_timeout(1000)
        if not self._contar(page, SEL_DATAS):
            raise RuntimeError("a lista de datas não carregou depois de escolher o mercado")
        page.wait_for_load_state("networkidle")
        return page.locator(SEL_DATAS)

    def datas(self, page):
        dsel = self._abrir(page)
        for tentativa in range(3):  # se a página ainda recarregar durante a leitura, lê de novo
            try:
                out = set()
                for o in dsel.locator("option").all():
                    ref = o.get_attribute("value")
                    d = parse_data(o.inner_text()) or parse_data(ref)
                    if d:
                        out.add((d, ref))
                return sorted(out)
            except Exception:  # noqa: BLE001
                if tentativa == 2:
                    raise
                page.wait_for_timeout(1500)

    def baixar(self, page, ref):
        ctx = page.context
        respostas, downloads = [], []

        def on_resp(r):
            if "pdf" in r.headers.get("content-type", "").lower():
                respostas.append(r)

        on_down = downloads.append

        def on_page(p):  # o PDF pode abrir em outra aba
            p.on("download", on_down)

        ctx.on("response", on_resp)
        ctx.on("page", on_page)
        page.on("download", on_down)
        try:
            self._abrir(page)
            page.select_option(SEL_DATAS, value=ref)   # pode recarregar a página também
            page.wait_for_timeout(1000)
            page.wait_for_load_state("networkidle")
            for s in BTN_OK:
                loc = page.locator(s)
                if loc.count():
                    loc.first.click()
                    break
            else:
                raise RuntimeError("botão Ok não encontrado")
            for _ in range(40):  # até ~20 s
                if respostas or downloads or self._link_pdf(ctx):
                    break
                page.wait_for_timeout(500)
            if respostas:
                return respostas[-1].body()
            if downloads:
                return Path(downloads[-1].path()).read_bytes()
            # Scriptcase costuma gravar o PDF em /_lib/tmp/sc_pdf_*.pdf e só mostrar um link
            url = self._link_pdf(ctx)
            if url:
                r = ctx.request.get(url, timeout=60000, ignore_https_errors=True)
                if r.ok and r.body()[:4] == b"%PDF":
                    return r.body()
            return None
        finally:
            ctx.remove_listener("response", on_resp)
            ctx.remove_listener("page", on_page)
            page.remove_listener("download", on_down)
            for p in ctx.pages:
                if p != page:
                    p.close()

    @staticmethod
    def _link_pdf(ctx):
        """Procura em todas as abas um link para o PDF gerado (ex.: .../_lib/tmp/sc_pdf_..._es.pdf)."""
        for p in ctx.pages:
            urls = [p.url]
            try:
                urls += re.findall(r'[\w./:-]*_lib/tmp/[\w.-]+\.pdf', p.content())
            except Exception:  # noqa: BLE001 (aba ainda carregando)
                continue
            for u in urls:
                if re.search(r"_lib/tmp/[\w.-]+\.pdf", u or ""):
                    return urljoin(p.url, u)
        return None

    def normalizar(self, linhas, data):
        """Tabela do boletim: DESCRIÇÃO | EMBALAGEM | MÍN | COMUM | MÁX | SITUAÇÃO (ME/MFI/MFR).
        A 1ª linha traz 'Data Pesquisada: dd/mm/aaaa', usada para conferir o dia do boletim."""
        data_pdf = None
        out, ignoradas = [], []
        for _pag, _ordem, _metodo, cel in linhas:
            texto = " ".join(c for c in cel if c)
            if "Data Pesquisada" in texto:
                data_pdf = parse_data(texto.split("Data Pesquisada", 1)[1])
                continue
            partes = self._colunas(cel)
            if not partes:
                if texto.strip() and not texto.strip().isdigit():
                    ignoradas.append(texto)
                continue
            c = cotacao(*partes, apelidos=APELIDOS, data_ok=data_pdf in (None, data))
            if c:
                out.append(c)
        if data_pdf and data_pdf != data:
            print(f"[ES] atenção: boletim pedido para {data}, PDF diz {data_pdf} (linhas ficam 'revisar')")
        revisar = sorted({f"{c['produto']} {c['detalhe']} [{c['embalagem']}]".strip()
                          for c in out if c["conferencia"] != "validado"})
        if revisar or ignoradas:
            fora = revisar + ignoradas
            print(f"[ES] {data}: {len(out) - len(revisar)} validadas; {len(fora)} fora do app: "
                  f"{fora[:10]}{' ...' if len(fora) > 10 else ''}")
        return out

    @staticmethod
    def _colunas(cel):
        """6 células já separadas, ou texto corrido (fallback) separado por regex."""
        cel = [c.strip() for c in cel]
        if len(cel) >= 5 and numero(cel[3]) is not None:
            return (cel + [""])[:6]
        m = LINHA.match(" ".join(c for c in cel if c))
        return m.groups() if m else None

    def discover(self, page, pasta):
        page.goto(URL, wait_until="networkidle", timeout=60000)
        (pasta / "pagina_inicial.html").write_text(page.content(), encoding="utf-8")
        for i in range(page.locator("select").count()):
            s = page.locator("select").nth(i)
            print(f"select #{i} id={s.get_attribute('id')} name={s.get_attribute('name')}")
            for o in s.locator("option").all()[:15]:
                print("   ", repr(o.get_attribute("value")), "|", o.inner_text().strip())
        try:
            datas = self.datas(page)
            print(f"\n{len(datas)} datas após escolher o mercado. Primeiras/últimas:",
                  datas[:3], "...", datas[-3:])
        except Exception as e:  # noqa: BLE001
            print("Falha ao carregar datas:", e)
        page.screenshot(path=str(pasta / "pagina.png"), full_page=True)
        print(f"Salvei {pasta}/pagina_inicial.html e pagina.png")
