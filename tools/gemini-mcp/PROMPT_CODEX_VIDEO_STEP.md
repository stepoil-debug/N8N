# Prompt para o Codex — Vídeo institucional STEP com Gemini/Veo

Use o MCP `gemini` configurado neste computador e trabalhe como diretor/editor de vídeo industrial.

Objetivo: criar um vídeo institucional premium da STEP para painel LED físico de 2 m x 1 m, proporção final 2:1, preferencialmente 3840x1920, duração alvo de 50 a 60 segundos, sem depender de áudio e com loop visual suave.

## Regras de segurança e arquivos

- Não leia histórico privado do Gemini.
- Não exclua chats, arquivos ou mídia remota.
- Não altere os vídeos originais.
- Trabalhe sempre em uma pasta de saída separada.
- Não exponha cookies, tokens ou credenciais em logs, prompts ou arquivos.

## Entrada

O usuário fornecerá:

- logo oficial da STEP;
- vários vídeos reais de referência/operação;
- opcionalmente fotos e materiais institucionais.

## Fluxo obrigatório

1. Confirme que `gemini_get_cookie_status` e `gemini_doctor` estão válidos.
2. Crie uma pasta de trabalho exclusiva para o projeto.
3. Inventarie todos os vídeos enviados: nome, duração, resolução e orientação.
4. Se necessário, use FFmpeg localmente para extrair frames/contact sheets dos vídeos, sem modificar os originais.
5. Analise os materiais e selecione apenas os melhores trechos/cenas. Priorize soldagem, faíscas, fabricação, engenharia, inspeção, equipamentos e escala industrial.
6. Analise a logo oficial e use suas cores e geometria como referência visual. Preserve a logo intacta quando ela aparecer.
7. Monte antes um storyboard de 50–60 s em blocos de aproximadamente 5–8 s.
8. Use `gemini_generate_media` com `media_type="video"` para gerar cenas complementares com Veo quando elas agregarem impacto. Quando útil, utilize um frame real ou a logo como `image_path` de referência.
9. Não gere uma única cena longa. Gere blocos consistentes e revise cada resultado antes de avançar.
10. Rejeite e regenere clipes com deformações, logos incorretas, EPI incoerente, mãos/equipamentos anômalos, soldagem irreal ou mudanças bruscas de identidade.
11. Monte o vídeo final com os melhores trechos reais e os clipes gerados. Use FFmpeg para cortes, crop/scale e concatenação quando necessário.
12. O resultado final deve ser 2:1. Preserve uma safe area central para logo e textos.
13. O vídeo deve funcionar sem áudio. Se houver áudio, ele é secundário.
14. Faça um loop suave: o final deve conectar visualmente ao início.

## Direção criativa

A cena hero é soldagem industrial realista e cinematográfica: arco elétrico intenso, faíscas bonitas, metal, fumaça, reflexos no capacete, profundidade e slow motion apenas onde fizer sentido.

Estética: engenharia pesada + tecnologia + oil & gas + filme publicitário industrial premium.

Evite aparência de slideshow, template genérico, apresentação corporativa antiga ou excesso de textos.

Estrutura sugerida:

- 0–5 s: impacto imediato com solda/faíscas;
- 5–15 s: fabricação e detalhes técnicos;
- 15–25 s: escala industrial e estruturas;
- 25–35 s: inspeção, precisão e qualidade;
- 35–45 s: pessoas + tecnologia;
- 45–53 s: clímax com soldagem/faíscas;
- 53–60 s: logo oficial STEP + `STEP PRIORIZA VOCÊ` + transição para o primeiro frame.

## Entregáveis

Entregue:

- storyboard aprovado em Markdown;
- lista dos arquivos/trechos escolhidos com timestamps;
- pasta dos clipes gerados;
- arquivo final master em MP4;
- versão otimizada para reprodução contínua no painel;
- relatório curto do que foi gerado por IA e do que veio dos vídeos reais.

Antes de iniciar gerações que consumam cota/créditos, apresente o storyboard e o plano de cenas para confirmação do usuário.
