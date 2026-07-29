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
- Testes e CI.

## Início rápido

```bash
cp .env.example .env
# altere todas as senhas, tokens e chaves
docker compose config
docker compose up -d --build
```

Acesse `http://localhost:5678`, crie o administrador e importe os JSONs da pasta `workflows/`.

## Fluxo

```text
Upload / e-mail / Supabase Storage
              ↓
             n8n
              ↓
      extração documental
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
