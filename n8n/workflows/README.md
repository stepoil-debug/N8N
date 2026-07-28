# Workflows n8n

Os workflows devem ser exportados como JSON, versionados neste diretório e tratados como código.

## Convenção de nomes

```text
WF-00__intake-opportunity.json
WF-01__register-documents.json
WF-02__extract-documents.json
WF-03__classify-documents.json
WF-04__triage-rfq.json
WF-05__extract-step-commitments.json
WF-06__validate-adherence.json
WF-07__deterministic-checks.json
WF-08__consolidate-audit.json
WF-09__human-review.json
WF-10__publish-results.json
WF-90__error-handler.json
WF-91__dead-letter-replay.json
WF-92__maintenance.json
```

## Regras obrigatórias

1. Cada workflow deve ter uma responsabilidade principal.
2. Workflows longos devem chamar subworkflows, não duplicar nós.
3. Toda execução recebe `correlation_id`, `opportunity_id` e `audit_run_id`.
4. Nós de IA devem retornar JSON estruturado e validado.
5. Arquivos grandes não devem ser transportados entre dezenas de nós; utilizar referências do Storage.
6. Toda gravação deve possuir chave de idempotência.
7. Retries devem ser aplicados somente a erros transitórios.
8. Erros devem terminar no `WF-90` com contexto suficiente para reprodução.
9. Nenhum workflow poderá enviar proposta ou publicar auditoria sem aprovação registrada.
10. Credenciais e IDs específicos de ambiente não podem ser fixados no JSON exportado.

## Padrão de entrada

```json
{
  "correlation_id": "uuid",
  "opportunity_id": "uuid",
  "audit_run_id": "uuid",
  "step": "triage_rfq",
  "skill_version": "0.2.0",
  "input_refs": [],
  "options": {}
}
```

## Padrão de saída

```json
{
  "status": "succeeded",
  "correlation_id": "uuid",
  "result_ref": "uuid",
  "warnings": [],
  "metrics": {},
  "error": null
}
```

## Nós permitidos por padrão

- Webhook e Respond to Webhook;
- Execute Workflow;
- HTTP Request para serviços internos aprovados;
- PostgreSQL/Supabase;
- IF, Switch, Merge, Loop e Wait;
- Set/Edit Fields;
- nós de modelo e parser estruturado aprovados;
- nós de notificação aprovados.

## Nós restritos

- Execute Command;
- acesso arbitrário ao sistema de arquivos;
- execução de código não versionado;
- chamadas HTTP para domínios não aprovados;
- nós comunitários sem revisão;
- envio de e-mail ou mensagem sem gate humano quando o conteúdo representar decisão da auditoria.

A lógica Python das skills deve ser executada no `audit-api`, não copiada para nós Code espalhados.
