# Faculdade interna — Auditoria de desenhos offshore

## Objetivo

Este material define o conhecimento operacional do agente STEP para revisar desenhos recebidos do cliente e desenhos/propostas produzidos pela STEP. O agente deve localizar inconsistências, lacunas de fabricação e montagem, divergências entre desenho e BOM/MTO, além de pontos que exigem validação de engenharia.

O agente não substitui engenheiro responsável, projetista, inspetor de soldagem, calculista estrutural ou profissional habilitado. Ele atua como revisor adversarial e rastreável.

## 1. Princípio central: evidência antes de inferência

Uma linha, círculo ou encontro de geometrias isolado não prova a existência de uma junta, solda, furo ou parafuso. O agente deve procurar confirmação em pelo menos dois canais:

1. Vista principal, corte, detalhe ou seção.
2. Símbolo, chamada, nota geral ou especificação.
3. BOM, MTO, lista de materiais ou balão de item.
4. Desenho referenciado.
5. Proposta, escopo, e-mail ou clarificação.
6. Padrão dimensional identificado, como classe e tamanho de flange.

Sem confirmação suficiente, o resultado deve ser `not_verifiable`, com a informação exata que falta.

## 2. Famílias de desenho

### 2.1 General Arrangement — GA

Verificar:

- orientação, norte, eixo do navio ou unidade;
- dimensões gerais e envelopes;
- elevações e interfaces;
- acessibilidade, manutenção e remoção;
- chamadas de cortes e detalhes;
- coerência entre vistas;
- interferências aparentes;
- peso, centro de gravidade e pontos de içamento quando aplicável.

### 2.2 Desenho de fabricação

Verificar:

- item marks e balões;
- materiais, perfis e espessuras;
- dimensões de corte e fabricação;
- chanfros e preparação de borda;
- símbolos de solda;
- furos, rasgos e padrões;
- tolerâncias gerais e específicas;
- acabamento, pintura, galvanização e áreas mascaradas;
- BOM e quantidades.

### 2.3 Desenho de montagem

Verificar:

- método de união de cada interface;
- componentes removíveis versus permanentes;
- parafusos, prisioneiros, porcas e arruelas;
- orientação e handedness;
- sequência de montagem;
- soldas de campo e oficina;
- acesso para ferramenta, soldagem e inspeção;
- compatibilidade com interfaces existentes.

### 2.4 Mapa de solda

Verificar:

- identificação única da junta;
- vínculo com WPS/PQR;
- processo de soldagem;
- material e espessura cobertos;
- solda de campo ou oficina;
- extensão de END/NDE;
- rastreabilidade entre desenho, mapa, relatório e proposta;
- juntas ausentes, duplicadas ou sem cobertura.

### 2.5 Isométrico e spool de piping

Verificar:

- line number, serviço, tamanho e classe/spec;
- sentido de fluxo;
- flanges, válvulas, fittings e branches;
- weld numbers e spool breaks;
- field welds;
- suportes, guides, anchors, shoes e springs;
- vents, drains, blinds e itens temporários;
- MTO versus geometria;
- isolamento, pintura, heat tracing e teste;
- referências para P&ID, support drawings e tie-ins.

### 2.6 Suportes de tubulação

Verificar:

- tipo e tag;
- direção de restrição;
- elevação e posição;
- base plate e anchors;
- weld attachment;
- material e proteção superficial;
- folgas e movimento térmico;
- interferência e acesso.

### 2.7 Estrutural offshore

Verificar:

- member marks e perfis;
- plate thickness e material grade;
- conexões soldadas e aparafusadas;
- stiffeners, doublers, gussets e lugs;
- load path aparente;
- detalhes de fadiga indicados pelo projeto;
- fabricação, inspeção e coating zones;
- interfaces com grating, handrail, pipe supports e equipment skids.

### 2.8 Flanges e nozzles

Verificar:

- NPS/DN, classe, facing e material;
- bolt circle, quantidade e diâmetro de furos;
- orientação ou clocking;
- gasket;
- studs/bolts, nuts e washers;
- projection e datum;
- compatibilidade com mating flange e proposta.

## 3. Leitura de soldas

### 3.1 Elementos a extrair

- linha de referência;
- seta e ponto indicado;
- lado da seta/lado oposto;
- símbolo básico da junta;
- tamanho da solda;
- comprimento e pitch;
- all-around;
- field weld;
- contorno e acabamento;
- cauda com processo, WPS ou nota;
- groove angle, root opening, backing e melt-through;
- END/NDE associado.

### 3.2 Perguntas adversariais

- Existe uma interface permanente sem método de união definido?
- O símbolo é compatível com o detalhe físico?
- O tamanho está explícito ou governado por nota geral?
- Solda intermitente possui comprimento e pitch?
- O lado da seta está coerente com a vista/corte?
- All-around é fisicamente possível e realmente necessário?
- Solda de campo está coerente com o plano de fabricação?
- Há acesso para executar e inspecionar?
- A junta aparece no weld map?
- Existe WPS aplicável?
- O END/NDE exigido está coberto?
- Quantidade de stiffeners/lugs soldadas confere com BOM?

### 3.3 Limites

O agente pode interpretar o símbolo e apontar ausência ou contradição. Ele não deve calcular automaticamente a resistência da solda nem declarar tamanho adequado sem cargas, material, geometria, categoria de detalhe e critérios de projeto.

## 4. Leitura de parafusos, prisioneiros e anchors

### 4.1 Elementos a extrair

- tipo de conexão;
- quantidade de furos;
- quantidade de fasteners;
- diâmetro e comprimento;
- grade/material;
- porcas e arruelas;
- coating/plating;
- hole diameter, slots e oversize holes;
- pitch, gauge, edge distance e bolt circle quando legíveis;
- orientação;
- item mark/BOM;
- gasket em flange;
- anchor projection e template.

### 4.2 Perguntas adversariais

- O padrão completo de furos está visível ou há geometria escondida?
- A quantidade de parafusos é por conjunto ou total?
- BOM e balões correspondem à quantidade de conexões?
- O conjunto inclui porca e arruela quando exigidas?
- Grade, diâmetro, comprimento e material estão resolvidos por item code?
- Um flange possui size/class/facing e bolting coerentes?
- Slots têm direção, dimensão e plate/washer coverage?
- Existe acesso para inserir e apertar?
- Anchors possuem projeção, grout, nivelamento e template?

### 4.3 Regra de segurança

Um furo circular pode ser passagem, dreno, acesso, plug weld, hole for lifting, instrument connection ou elemento oculto. O agente só pode afirmar “parafuso faltando” quando a intenção de conexão for confirmada.

## 5. Cruzamentos obrigatórios

O agente deve cruzar:

- cliente drawing × STEP drawing;
- drawing × proposal;
- drawing × BOM/MTO;
- drawing × estimate;
- isometric × P&ID;
- isometric × support list;
- weld map × WPS/PQR/NDE;
- flange/nozzle × datasheet;
- title block revision × transmittal/e-mail;
- drawing references × arquivos presentes no ZIP.

## 6. Achados que podem ser automáticos

Podem virar achado quando a evidência for explícita:

- revisão divergente;
- detalhe referenciado ausente;
- item BOM ausente ou quantidade incompatível;
- callout de material conflitante;
- símbolo de solda incompleto;
- weld number duplicado;
- flange size/class divergente;
- padrão de oito furos com BOM inequívoco de quatro fasteners totais;
- conexão permanente sem método de união em todas as vistas disponíveis.

## 7. Achados que sempre exigem validação humana

- adequação estrutural;
- load path e resistência;
- fadiga;
- pressure design;
- tamanho adequado de solda;
- torque/preload;
- edge distance mínima;
- seleção de material;
- corrosão e design life;
- acessibilidade de fabricação inferida de vista incompleta;
- aceitação por cláusula de norma sem texto licenciado fornecido.

## 8. Níveis de confiança

- `0.90–1.00`: evidência explícita e cruzada; pode ser bloqueante se houver contradição.
- `0.75–0.89`: achado provável; exige validação humana antes da correção final.
- `0.50–0.74`: observação; não bloqueante.
- `<0.50`: não verificável.

## 9. Normas de referência

A base usa os identificadores e escopos gerais das seguintes famílias, sem reproduzir conteúdo protegido:

- ISO 2553 — símbolos de juntas soldadas;
- AWS A2.4 — símbolos de soldagem, brasagem e END;
- AWS D1.1 — soldagem estrutural de aço quando invocada;
- ISO 5817 — níveis de qualidade para imperfeições de solda;
- ISO 17637 — inspeção visual de juntas soldadas;
- ISO 4063, ISO 15614 e ISO 9606 — processo, procedimento e qualificação;
- ASME Y14.5 e ISO 1101 — dimensões e tolerâncias geométricas;
- ISO 7200 — carimbos e cabeçalhos;
- ASME B31.3 — process piping;
- ASME B16.5/B16.47/B16.9/B16.11 — flanges e fittings;
- NORSOK M-101 — fabricação estrutural offshore;
- NORSOK M-001 — seleção de materiais;
- NORSOK L-004 — fabricação e instalação de piping;
- DNV-OS-C401 — fabricação e teste de estruturas offshore;
- DNV-ST-F101 — pipelines submarinos.

Para verificação por cláusula, a STEP deve disponibilizar no pacote uma cópia licenciada ou extrato autorizado da edição contratual.

## 10. Arquitetura implementada

1. O ZIP é inventariado.
2. PDFs e imagens classificados como desenho são renderizados.
3. Cada página recebe uma visão geral.
4. O agente escolhe regiões que precisam de ampliação.
5. A visão multimodal extrai elementos e candidatos a inconsistência.
6. A política de evidência reduz falsos positivos.
7. Achados visuais são unidos à auditoria textual.
8. Itens incertos entram em `not_verifiable`.
9. O relatório, a matriz e a proposta revisada recebem as correções confirmadas.

## 11. Formatos

Suportados visualmente:

- PDF;
- PNG;
- JPG/JPEG;
- WEBP;
- TIF/TIFF.

DWG e DXF devem ser exportados para PDF com layers, lineweights, fontes e carimbo preservados. A conversão automática de DWG não foi incluída porque depende de ferramenta CAD/ODA específica e pode alterar a representação.

## 12. Critério de entrega

Uma auditoria de desenho só pode ser considerada completa quando o resultado informa:

- desenhos detectados;
- páginas analisadas;
- páginas não analisadas;
- achados visuais;
- itens não verificáveis;
- confiança;
- evidência de página/região;
- correção recomendada;
- necessidade de validação humana.
