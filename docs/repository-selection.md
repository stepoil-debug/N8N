# Seleção da base n8n

## Decisão

Usar o repositório oficial **`n8n-io/n8n-hosting` como referência de infraestrutura**, sem fazer um fork integral. Incorporar seletivamente padrões do **`n8n-io/self-hosted-ai-starter-kit`** para desenvolvimento local de IA.

## Por que não copiar um template comunitário inteiro

A plataforma manipulará RFQs, propostas comerciais, preços, obrigações contratuais e documentos técnicos. Portanto, atualizações, segurança, rastreabilidade e previsibilidade operacional têm prioridade sobre a quantidade de integrações prontas de um template.

Templates comunitários podem ser utilizados como pesquisa, mas não como dependência estrutural sem auditoria de:

- imagens Docker e versões utilizadas;
- armazenamento e exposição de credenciais;
- portas publicadas;
- scripts de instalação;
- política de atualização;
- licença;
- telemetria e serviços externos;
- recuperação de falhas e backup.

## Avaliação

| Base | Pontos fortes | Limitações | Uso no projeto |
|---|---|---|---|
| `n8n-io/n8n-hosting` | Oficial, exemplos de hospedagem e componentes de produção | Não resolve a lógica de auditoria | Referência principal de implantação |
| `n8n-io/self-hosted-ai-starter-kit` | Integra rapidamente n8n e componentes de IA local | Direcionado a início rápido e prova de conceito | Referência de desenvolvimento, não base integral |
| `n8n-io/n8n` | Código-fonte oficial do produto | Não é um template da nossa aplicação | Consulta técnica e compatibilidade |
| Templates comunitários | Podem trazer dashboards e automações prontas | Qualidade, segurança e manutenção variáveis | Somente pesquisa e adoção seletiva |

## Princípio de atualização

Não manteremos uma cópia modificada do repositório oficial. O projeto possuirá seu próprio `docker-compose.yml`, imagens fixadas por versão e documentação das decisões. Isso permite atualizar n8n, Redis e PostgreSQL de forma controlada sem resolver conflitos de um fork grande.

## Componentes escolhidos

- n8n principal para editor, API, timers e coordenação;
- um ou mais n8n workers para execuções em fila;
- PostgreSQL exclusivo para o estado interno do n8n;
- Redis exclusivo para a fila;
- Supabase para o domínio de auditoria e Storage;
- serviço `audit-api` para processamento documental e execução das skills;
- proxy reverso com TLS;
- CI para validar workflows, schemas, Python e arquivos Docker;
- backups e observabilidade definidos separadamente.

## Decisões específicas da STEP

1. Documentos não trafegarão entre workflows como binários grandes. O n8n receberá referências de objetos no Supabase Storage.
2. Prompts, schemas e versões das skills serão mantidos no Git, e não somente dentro de nós visuais.
3. A IA não poderá publicar, enviar ou aprovar propostas.
4. Todo achado deverá apontar evidência identificável.
5. Ausência de evidência resultará em `not_verifiable`, nunca em suposição.
6. Operações deverão ser idempotentes para permitir reprocessamento seguro.
