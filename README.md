# STEP Industrial Audit — n8n

Plataforma isolada para auditar propostas industriais da STEP contra RFQs, desenhos, e-mails, planilhas e condições comerciais do cliente.

## O que o sistema faz

O usuário envia um único ZIP contendo os documentos do cliente e os documentos STEP. O sistema:

1. Descompacta, inventaria e classifica os arquivos.
2. Extrai PDF, Word, Excel, CSV, TXT, EML e MSG, aplicando OCR quando necessário.
3. Renderiza desenhos PDF/imagem e executa leitura visual multimodal de pranchas, vistas, cortes, detalhes, BOM/MTO, soldas, furos, flanges e conexões aparafusadas.
4. Extrai todos os requisitos do cliente e os compromissos assumidos pela STEP.
5. Compara requisito por requisito e classifica como atendido, parcial, não atendido ou não verificável.
6. Identifica inconsistências técnicas, comerciais, contratuais, de prazo, quantidade, materiais, normas, qualidade, documentação e desenhos.
7. Informa impacto, severidade, evidências, página/região e correção necessária para cada achado.
8. Gera uma proposta técnico-comercial revisada sem inventar preços, prazos ou obrigações.
9. Marca como validação humana obrigatória toda correção que dependa de decisão comercial, cálculo, código de projeto ou interpretação visual sem evidência suficiente.

## Leitura de desenhos offshore

O motor visual foi preparado para revisar:

- General Arrangement e layouts;
- desenhos de fabricação e montagem;
- estruturas, plates, profiles, stiffeners, lugs e supports;
- weld maps e símbolos de soldagem;
- piping isometrics e spool drawings;
- pipe supports, guides, anchors e shoes;
- flanges, nozzles e interfaces;
- BOM, MTO, balões, quantidades e revisões.

As verificações incluem solda sem definição, símbolo incompleto, lado da solda, comprimento/pitch, all-around/field weld, rastreabilidade WPS/NDE, padrão de furos, quantidade de parafusos, conjunto incompleto de bolt/nut/washer, flange incompatível, slot indefinido, anchor/base plate incompleto, divergência BOM versus desenho e detalhe referenciado ausente.

O agente não considera automaticamente que um círculo é um furo para parafuso ou que duas peças em contato exigem solda. Um achado bloqueante exige evidência cruzada ou contradição explícita. Pontos relacionados a resistência, fadiga, pressure design, weld sizing, torque/preload e adequação normativa permanecem sujeitos a validação de profissional qualificado.

A ontologia executável está em `knowledge/offshore_drawing_rules.json`; o estudo operacional está em `docs/offshore-drawing-audit-knowledge.md`.

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
FastAPI documental + renderização de desenhos + n8n efêmeros
    ↓
GitHub Models — texto e visão
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
- Imagens renderizadas dos desenhos permanecem apenas no runner temporário e são excluídas ao final.

## Componentes principais

- `site/`: interface do GitHub Pages.
- `site/config.js`: configuração pública segura da fila.
- `scripts/queue_worker.py`: ponte segura entre fila, n8n e artefatos.
- `.github/workflows/process-audit.yml`: worker agendado e manual.
- `workflows/parts/`: workflow n8n compatível com GitHub Models, armazenado de forma compactada.
- `apps/document-api/`: extração documental, visão de desenhos e geração dos cinco artefatos.
- `apps/document-api/app/drawing_vision.py`: renderização e análise multimodal das pranchas.
- `knowledge/offshore_drawing_rules.json`: regras rastreáveis de soldagem, bolting, piping e integridade de desenho.
- `docs/offshore-drawing-audit-knowledge.md`: estudo técnico e critérios de decisão.
- `supabase/migrations/002_async_audit_queue.sql`: estrutura reproduzível da fila e buckets.
- `.github/workflows/e2e-audit-test.yml`: teste ponta a ponta com documentos fictícios.

## Fluxo do worker

O workflow `Process STEP Audit Queue`:

1. Solicita um token OIDC temporário.
2. Reivindica atomicamente o próximo trabalho da fila.
3. Baixa o ZIP por URL assinada.
4. Instala e inicia FastAPI e n8n em um runner descartável.
5. Usa o `GITHUB_TOKEN` temporário para consultar GitHub Models.
6. Extrai os documentos e renderiza os desenhos detectados.
7. Executa leitura visual por página e, quando necessário, por região ampliada.
8. Cruza desenho, BOM/MTO, proposta e requisitos do cliente.
9. Executa auditoria, correções e geração da proposta revisada.
10. Envia os artefatos ao bucket privado.
11. Marca o trabalho como concluído ou registra a falha.
12. Exclui todos os arquivos temporários do runner.

O painel acompanha automaticamente os estados `queued`, `processing`, `completed` e `failed`, inclusive após recarregar a página.

## Formatos de desenho

Leitura visual direta:

- PDF;
- PNG;
- JPG/JPEG;
- WEBP;
- TIF/TIFF.

Arquivos DWG e DXF devem ser exportados para PDF preservando layers, lineweights, fontes, carimbo e revisões. A conversão automática de CAD não foi incluída porque ferramentas diferentes podem alterar a representação ou omitir referências externas.

## Execução local alternativa

O projeto continua incluindo `docker-compose.yml` para quem preferir uma instalação permanente com PostgreSQL, Redis, n8n, FastAPI e Ollama. Para leitura visual local, deve ser configurado um modelo multimodal compatível com o endpoint escolhido; o modelo textual padrão não deve ser presumido como capaz de interpretar imagens.

## Confidencialidade

Documentos PERENCO e de outros clientes não são versionados neste repositório. O teste automatizado utiliza somente uma oportunidade fictícia criada durante a execução do GitHub Actions.
