-- Esquema do banco de cotações (idempotente: pode rodar a cada execução)
set client_min_messages = warning;

create table if not exists ceasa (
    id    text primary key,          -- ex.: 'ES'
    nome  text not null,             -- rótulo exibido no app
    uf    text not null,
    ativo boolean not null default true
);

-- Um registro por boletim (CEASA + dia), com o status do download
create table if not exists boletim (
    ceasa_id     text not null references ceasa(id),
    data         date not null,
    status       text not null,                 -- ok | sem_pdf | erro
    pdf_sha256   text,
    erro         text,
    tentativas   int  not null default 1,
    normalizado  boolean not null default false, -- já virou linhas em "cotacao"?
    coletado_em  timestamptz not null default now(),
    primary key (ceasa_id, data)
);

-- Linhas cruas do PDF, exatamente como saíram (permite reprocessar sem baixar de novo)
create table if not exists linha_bruta (
    ceasa_id text not null,
    data     date not null,
    pagina   int  not null,
    ordem    int  not null,
    metodo   text not null,                     -- tabela | texto
    celulas  text[] not null,
    primary key (ceasa_id, data, pagina, ordem),
    foreign key (ceasa_id, data) references boletim(ceasa_id, data) on delete cascade
);

-- Cotações já padronizadas (mesmos campos da planilha consolidada)
create table if not exists cotacao (
    ceasa_id    text not null,
    data        date not null,
    produto     text not null,                  -- "Produto padrão" (ver GRUPOS em gerar_dados.py)
    detalhe     text not null default '',
    embalagem   text not null,                  -- chave de EMB em gerar_dados.py (KG, CX 30 DZ...)
    minimo      numeric(10,2),
    comum       numeric(10,2) not null,
    maximo      numeric(10,2),
    situacao    text,                           -- firme | fraco | estável
    conferencia text not null default 'pendente', -- só 'validado' vai para o app
    primary key (ceasa_id, data, produto, detalhe, embalagem),
    foreign key (ceasa_id, data) references boletim(ceasa_id, data) on delete cascade
);

create index if not exists cotacao_data_idx on cotacao (data);
