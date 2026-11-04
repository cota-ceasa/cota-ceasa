# COTA CEA$A — coleta automática

GitHub Actions (agendador) → Playwright baixa os boletins → Postgres (Neon/Supabase) →
`docs/dados.json` → GitHub Pages serve o app.

```
docs/                    app (PWA) publicado no GitHub Pages
coleta/run.py            orquestra: baixar → gravar → normalizar → exportar
coleta/ceasas/es.py      coletor da CEASA-ES (1 arquivo por CEASA)
coleta/schema.sql        tabelas: ceasa, boletim, linha_bruta, cotacao
coleta/gerar_dados.py    cotações → dados.json (também aceita a planilha antiga)
.github/workflows/       agendamento (seg–sáb, 12:17 e 18:47 de Brasília)
```

## Configuração (uma vez, ~10 min)

1. **Banco**: crie um projeto grátis no [Neon](https://neon.tech) (ou Supabase) e copie a
   *connection string* (`postgresql://...?sslmode=require`). As tabelas são criadas sozinhas.
2. **Repositório**: crie um repo **público** no GitHub e suba esta pasta
   (público = Actions sem limite de minutos e Pages grátis; nenhum segredo fica no código).
3. **Segredo**: Settings → Secrets and variables → Actions → *New secret*
   `DATABASE_URL` = a connection string.
4. **Pages**: Settings → Pages → Source: **GitHub Actions**.

## Primeira execução

Actions → **Coleta CEASA** → *Run workflow*:

1. `discover = ES` → baixe o artefato **saida** (print + HTML do formulário) e confira.
2. `inicio = 2026-01-01`, `max = 200` → carga histórica. Os PDFs ficam no artefato **saida** por 7 dias.
3. Depois disso o agendamento cuida dos boletins novos.

> **Status atual (ES):** o coletor lê a tabela HTML do boletim (página boletim_completo_es.php),
> sem gerar PDF. Testado com o boletim real de 20/08/2026: 171 linhas, 171 validadas.
> Linhas que não passam na conferência (produto desconhecido, embalagem fora de `EMB`,
> mín > comum > máx, data do boletim diferente da pedida) ficam no banco como `revisar`,
> aparecem no log e não vão para o app.

## Adicionar outra CEASA

1. Crie `coleta/ceasas/mg.py` herdando de `Coletor` e implemente `datas()`, `baixar()` e
   `normalizar()` (veja `es.py`).
2. Registre em `coleta/ceasas/__init__.py`.
3. A CEASA aparece sozinha no seletor de localidade do app.

`normalizar()` deve devolver `produto` com o nome padrão (`GRUPOS` em `gerar_dados.py`) e
`embalagem` com uma chave de `EMB`. Só linhas com `conferencia='validado'` vão para o app.

## Rodar no seu computador

```bash
pip install -r requirements.txt && python -m playwright install chromium
export DATABASE_URL="postgresql://..."      # Windows: set DATABASE_URL=...
python -m coleta.run --ceasa ES --headed      # mostra o navegador
python -m http.server -d docs 8000            # testar o app em http://localhost:8000
```

Gerar a partir da planilha antiga: `python -m coleta.gerar_dados ceasa_consolidado_geral.xlsx docs/dados.json`
