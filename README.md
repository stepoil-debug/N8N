# STEP Industrial Audit — n8n

Projeto isolado para automatizar a triagem de RFQs e a validação adversarial de propostas industriais da STEP.

## Incluído

- n8n em modo fila com PostgreSQL, Redis, worker e task runners externos.
- API FastAPI para extração de PDF, Excel, Word, CSV, TXT, EML e MSG.
- Geração determinística do checklist Excel da Etapa 1.
- Inventário integral do checklist e geração do PDF de aderência da Etapa 2.
- Bloqueio do relatório quando houver requisito aplicável sem cobertura.
- Workflows importáveis no n8n.
- Migration Supabase para oportunidades, documentos, requisitos, compromissos, execuções, achados e artefatos.
- Painel web responsivo na pasta `site/`.
- Deploy automático do painel pelo GitHub Pages.
- Proxy autenticado da API para encaminhar auditorias ao n8n sem expor o webhook.
- Testes e CI.

## Painel web

O frontend é publicado pelo workflow `.github/workflows/deploy-pages.yml` sempre que houver alteração na pasta `site/`.

URL esperada:

```text
https://stepoil-debug.github.io/N8N/
```

O painel permite:

- Cadastrar uma oportunidade.
- Separar documentos do cliente e documentos da STEP.
- Testar conexão com a API documental.
- Extrair arquivos diretamente pela API protegida.
- Encaminhar a auditoria ao n8n por uma rota interna segura.
- Acompanhar um histórico local sem armazenar documentos no GitHub.

A URL pública da API fica no `localStorage` do navegador. O token fica apenas no `sessionStorage` e é apagado quando a aba é fechada. A URL do webhook do n8n permanece somente no `.env` do servidor.

> O GitHub Pages hospeda somente HTML, CSS e JavaScript. O n8n, a API Python, o PostgreSQL, o Redis e o Supabase precisam permanecer em infraestrutura própria.

## Início rápido do backend

```bash
cp .env.example .env
# altere todas as senhas, tokens e chaves
docker compose config
docker compose up -d --build
```

Acesse `http://localhost:5678`, crie o administrador e importe os JSONs da pasta `workflows/`.

Em produção, publique a API atrás de HTTPS e configure:

```env
DOCUMENT_API_CORS_ALLOWED_ORIGINS=https://stepoil-debug.github.io
N8N_AUDIT_WEBHOOK_URL=http://n8n:5678/webhook/step-audit
N8N_AUDIT_WEBHOOK_TOKEN=troque-por-um-token-interno
```

## Fluxo

```text
Painel GitHub Pages
          ↓
API documental autenticada
          ↓
proxy interno → n8n
          ↓
extração e classificação
          ↓
triagem RFQ → checklist Excel
          ↓
requisitos × proposta STEP
          ↓
validações técnicas/comerciais/contratuais
          ↓
aprovação humana → PDF + JSON + dashboard
```

Documentos PERENCO e de outros clientes não são versionados neste repositório.
