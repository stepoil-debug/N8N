# STEP Industrial Audit — n8n

Plataforma isolada para auditar propostas industriais da STEP contra RFQs, desenhos, e-mails, planilhas e condições comerciais do cliente.

## Resultado esperado

O usuário envia um único ZIP contendo os documentos do cliente e os documentos STEP. O sistema:

1. Descompacta, inventaria e classifica os arquivos.
2. Extrai o conteúdo de PDF, Word, Excel, CSV, TXT, EML e MSG, aplicando OCR quando necessário.
3. Extrai todos os requisitos do cliente e os compromissos assumidos pela STEP.
4. Compara requisito por requisito e marca: atendido, parcial, não atendido ou não verificável.
5. Identifica inconsistências técnicas, comerciais, contratuais, de prazo, quantidade, material, normas, qualidade e documentação.
6. Informa o impacto e a correção necessária para cada achado.
7. Gera uma proposta técnico-comercial revisada, sem inventar preço, prazo ou obrigação sem evidência.
8. Marca como validação humana obrigatória toda correção que dependa de decisão comercial ou técnica.

## Entregáveis por auditoria

- `Relatorio_Auditoria_<oportunidade>.pdf`
- `Proposta_Revisada_<oportunidade>.docx`
- `Proposta_Revisada_<oportunidade>.pdf`
- `Auditoria_Completa_<oportunidade>.xlsx`
- `Auditoria_Completa_<oportunidade>.json`

O painel só registra **Análise concluída** depois que os achados e todos os artefatos forem gerados. A ausência do n8n ou do modelo de IA produz erro explícito; não existe mais sucesso apenas por classificar o ZIP.

## Componentes

- n8n em modo fila com PostgreSQL, Redis, worker e task runners externos.
- API FastAPI para extração documental e geração dos artefatos.
- Ollama com modelo local, sem exigir uma API de IA paga.
- Workflow `workflows/40-auditoria-completa.json` para extração, auditoria, correção e consolidação.
- Supabase opcional para persistência corporativa.
- Painel web responsivo publicado pelo GitHub Pages.
- Testes automatizados, validação dos workflows e CI.

## Painel web

```text
https://stepoil-debug.github.io/N8N/
```

O usuário final precisa apenas:

1. Abrir **Nova auditoria**.
2. Selecionar um ZIP completo da oportunidade.
3. Conferir a separação preliminar.
4. Confirmar oportunidade, cliente e RFQ.
5. Clicar em **Executar auditoria completa**.
6. Abrir a aba **Resultado** para consultar achados, correções e downloads.

O painel não solicita URL técnica, token ou chave de IA ao usuário. O endereço do backend fica definido internamente em `site/config.js`.

Arquivos como `Thumbs.db`, `.DS_Store`, `desktop.ini` e temporários do Office são ignorados. Caminhos inseguros, excesso de entradas, arquivos internos muito grandes e taxas de compressão suspeitas são bloqueados.

> GitHub Pages executa somente a interface. n8n, FastAPI, PostgreSQL, Redis e Ollama precisam ser executados em um servidor ou computador com Docker.

## Inicialização do backend

```bash
cp .env.example .env
# altere senhas e tokens

docker compose config
docker compose up -d --build
```

Na primeira inicialização, o Docker baixa o modelo configurado em `OLLAMA_MODEL`. O padrão do projeto é `qwen3:14b`.

Acesse o n8n, crie o administrador, importe e ative:

```text
workflows/40-auditoria-completa.json
```

O webhook ativo deve ser:

```text
http://n8n:5678/webhook/step-audit
```

Variáveis essenciais:

```env
N8N_AUDIT_WEBHOOK_URL=http://n8n:5678/webhook/step-audit
N8N_AUDIT_WEBHOOK_TOKEN=troque-por-um-token-interno
DOCUMENT_API_URL=http://document-api:8000
DOCUMENT_API_KEY=troque-por-um-segredo-de-api
LLM_BASE_URL=http://ollama:11434/api/chat
LLM_MODEL=qwen3:14b
OLLAMA_MODEL=qwen3:14b
CORS_ALLOWED_ORIGINS=https://stepoil-debug.github.io
```

Para uso externo, publique a API atrás de HTTPS. Depois ajuste somente o arquivo técnico:

```js
window.STEP_AUDIT_CONFIG = Object.freeze({
  apiBaseUrl: 'https://servico-auditoria.exemplo.com',
  maxZipMb: 250
});
```

## Fluxo

```text
ZIP completo
    ↓
extração e classificação
    ↓
requisitos do cliente
    ×
compromissos STEP
    ↓
achados + severidade + evidências
    ↓
correções recomendadas
    ↓
proposta revisada para validação humana
    ↓
PDF + DOCX + XLSX + JSON
```

Documentos PERENCO e de outros clientes não são versionados neste repositório.
