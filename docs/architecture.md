# Arquitetura

O n8n é o orquestrador. A API documental executa tarefas determinísticas e os agentes especialistas produzem JSON estruturado.

## Componentes

- `n8n`: editor, webhooks e coordenação.
- `n8n-worker`: execução em fila.
- `Redis`: fila Bull.
- `PostgreSQL`: estado interno do n8n.
- `document-api`: extração, Excel, inventário e PDF.
- `Supabase`: documentos, evidências, requisitos, compromissos, achados e histórico.

## Regras de segurança

1. Nenhum documento de cliente no GitHub.
2. Sem documento, página/seção e trecho, o resultado deve ser `not_verifiable`.
3. Achados críticos bloqueiam submissão até decisão humana.
4. Segredos ficam no `.env` ou no gerenciador de credenciais do n8n.
5. Bucket Supabase privado com signed URLs de curta duração.
