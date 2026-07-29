# STEP Industrial Audit — n8n

Plataforma isolada para auditar propostas industriais da STEP contra RFQs, desenhos, e-mails, planilhas e condições comerciais do cliente.

## O que o sistema faz

O usuário envia um único ZIP contendo os documentos do cliente e os documentos STEP. O sistema:

1. Descompacta, inventaria e classifica os arquivos.
2. Extrai PDF, Word, Excel, CSV, TXT, EML e MSG, aplicando OCR quando necessário.
3. Extrai todos os requisitos do cliente e os compromissos assumidos pela STEP.
4. Compara requisito por requisito e classifica como atendido, parcial, não atendido ou não verificável.
5. Identifica inconsistências técnicas, comerciais, contratuais, de prazo, quantidade, materiais, normas, qualidade e documentação.
6. Informa impacto, severidade, evidências e correção necessária para cada achado.
7. Gera uma proposta técnico-comercial revisada sem inventar preços, prazos ou obrigações.
8. Marca como validação humana obrigatória toda correção que dependa de decisão comercial ou técnica.

## Entregáveis

Cada auditoria concluída gera:

- `Relatorio_Auditoria_<oportunidade>.pdf`
- `Proposta_Revisada_<oportunidade>.docx`
- `Proposta_Revisada_<oportunidade>.pdf`
- `Auditoria_Completa_<oportunidade>.xlsx`
- `Auditoria_Completa_<oportunidade>.json`

Quando o ZIP contém uma proposta STEP em Word, o documento original é usado como base. O sistema tenta aplicar as correções diretamente e inclui um anexo de auditoria com os pontos aplicados e os itens pendentes de validação humana.

## Painel

```text
https://stepoil-debug.github.io/N8N/
```

O usuário final precisa apenas:

1. Abrir **Nova auditoria**.
2. Selecionar o ZIP completo da oportunidade.
3. Conferir a separação preliminar.
4. Confirmar oportunidade, cliente e RFQ.
5. Clicar em **Executar auditoria completa**.
6. Aguardar o processamento assíncrono.
7. Abrir **Resultado** para consultar achados, correções e downloads.

O painel não solicita URL técnica, token ou chave de IA.

## Arquitetura operacional

```text
GitHub Pages
    ↓
Supabase Edge Function
    ↓
ZIP em bucket privado + trabalho na fila
    ↓
GitHub Actions a cada 5 minutos
    ↓
FastAPI documental + n8n efêmeros
    ↓
GitHub Models
    ↓
relatório + proposta revisada + Excel + JSON
    ↓
resultados em bucket privado com links temporários
```

### Segurança

- Os ZIPs e resultados não são armazenados no GitHub.
- Os buckets `step-audit-inputs` e `step-audit-outputs` são privados.
- Cada auditoria recebe um token aleatório mantido apenas no navegador do solicitante.
- O token é armazenado no banco somente como hash SHA-256.
- O worker autentica na Edge Function com OIDC temporário emitido pelo GitHub.
- A Edge Function aceita o worker apenas para este repositório, workflow e branch.
- Não existe `service_role`, token de IA ou senha gravada no frontend.
- Os pacotes possuem expiração de sete dias.
- Caminhos inseguros, excesso de entradas e compactação suspeita são bloqueados.

## Componentes principais

- `site/`: interface do GitHub Pages.
- `site/config.js`: configuração pública segura da fila.
- `scripts/queue_worker.py`: ponte segura entre fila, n8n e artefatos.
- `.github/workflows/process-audit.yml`: worker agendado e manual.
- `workflows/parts/`: workflow n8n compatível com GitHub Models, armazenado de forma compactada.
- `apps/document-api/`: extração documental e geração dos cinco artefatos.
- `supabase/migrations/002_async_audit_queue.sql`: estrutura reproduzível da fila e buckets.
- `.github/workflows/e2e-audit-test.yml`: teste ponta a ponta com documentos fictícios.

## Fluxo do worker

O workflow `Process STEP Audit Queue`:

1. Solicita um token OIDC temporário.
2. Reivindica atomicamente o próximo trabalho da fila.
3. Baixa o ZIP por URL assinada.
4. Instala e inicia FastAPI e n8n em um runner descartável.
5. Usa o `GITHUB_TOKEN` temporário para consultar GitHub Models.
6. Executa extração, auditoria, correções e geração da proposta revisada.
7. Envia os artefatos ao bucket privado.
8. Marca o trabalho como concluído ou registra a falha.
9. Exclui todos os arquivos temporários do runner.

O painel acompanha automaticamente os estados `queued`, `processing`, `completed` e `failed`, inclusive após recarregar a página.

## Execução local alternativa

O projeto continua incluindo `docker-compose.yml` para quem preferir uma instalação permanente com PostgreSQL, Redis, n8n, FastAPI e Ollama. Essa alternativa não é necessária para o funcionamento do painel assíncrono.

## Confidencialidade

Documentos PERENCO e de outros clientes não são versionados neste repositório. O teste automatizado utiliza somente uma oportunidade fictícia criada durante a execução do GitHub Actions.
