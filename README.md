# STEP Industrial Audit — n8n

Projeto isolado para automatizar a triagem de RFQs e a validação adversarial de propostas industriais da STEP.

## Incluído

- n8n em modo fila com PostgreSQL, Redis, worker e task runners externos.
- API FastAPI para extração de PDF, Excel, Word, CSV, TXT, EML e MSG.
- Upload único em ZIP para cada oportunidade.
- Inventário e classificação automática por pasta, nome, formato e conteúdo.
- Separação automática entre documentos do cliente, documentos STEP e itens a confirmar.
- Preservação do caminho original do ZIP como referência de evidência.
- Geração determinística do checklist Excel da Etapa 1.
- Inventário integral do checklist e geração do PDF de aderência da Etapa 2.
- Bloqueio do relatório quando houver requisito aplicável sem cobertura.
- Workflows importáveis no n8n.
- Migration Supabase para oportunidades, documentos, requisitos, compromissos, execuções, achados e artefatos.
- Painel web responsivo na pasta `site/`.
- Deploy automático do painel pelo GitHub Pages.
- Testes e CI.

## Painel web

O frontend é publicado pelo workflow `.github/workflows/deploy-pages.yml` sempre que houver alteração na pasta `site/`.

```text
https://stepoil-debug.github.io/N8N/
```

O usuário final precisa apenas:

1. Abrir uma nova auditoria.
2. Selecionar um único arquivo ZIP com toda a oportunidade.
3. Conferir o inventário gerado automaticamente.
4. Confirmar os dados da oportunidade e executar.

O painel não solicita URL, token ou configuração técnica. A separação preliminar do ZIP ocorre no próprio navegador. Quando o serviço de processamento estiver publicado, seu endereço será definido internamente em `site/config.js`.

Arquivos como `Thumbs.db`, `.DS_Store`, `desktop.ini` e temporários do Office são ignorados. Caminhos inseguros, excesso de entradas, arquivos internos muito grandes e taxas de compressão suspeitas são bloqueados.

> O GitHub Pages hospeda somente HTML, CSS e JavaScript. O processamento completo de PDF, MSG, OCR, n8n, PostgreSQL, Redis e Supabase permanece na infraestrutura de execução.

## Início rápido do backend

```bash
cp .env.example .env
# altere todas as senhas, tokens e chaves
docker compose config
docker compose up -d --build
```

Acesse `http://localhost:5678`, crie o administrador e importe os JSONs da pasta `workflows/`.

Em produção, publique o serviço atrás de HTTPS e configure internamente:

```env
CORS_ALLOWED_ORIGINS=https://stepoil-debug.github.io
N8N_AUDIT_WEBHOOK_URL=http://n8n:5678/webhook/step-audit/run
N8N_AUDIT_WEBHOOK_TOKEN=troque-por-um-token-interno
MAX_PACKAGE_MB=250
MAX_ZIP_ENTRIES=2500
MAX_ZIP_UNCOMPRESSED_MB=1500
```

Depois, informe o endereço público apenas no arquivo técnico `site/config.js`:

```js
window.STEP_AUDIT_CONFIG = Object.freeze({
  apiBaseUrl: 'https://servico-auditoria.exemplo.com',
  maxZipMb: 250
});
```

## Fluxo

```text
ZIP completo da oportunidade
          ↓
inventário local no navegador
          ↓
classificação automática
          ↓
serviço documental → n8n
          ↓
extração de conteúdo e OCR
          ↓
requisitos do cliente × compromissos STEP
          ↓
validações técnicas/comerciais/contratuais
          ↓
aprovação humana → PDF + JSON + checklist + dashboard
```

Documentos PERENCO e de outros clientes não são versionados neste repositório.
