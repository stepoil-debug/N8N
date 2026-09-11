# STEP — Gemini Web MCP no Codex

Este pacote prepara o Codex no Windows para acessar o Gemini Web via MCP usando o projeto público `Luckycat133/gemini-web-mcp`.

> Atenção: esse MCP usa comportamento do Gemini Web obtido por engenharia reversa. O próprio projeto alerta para possível risco de conta/termos do Google. Prefira uma conta Google dedicada.

## O que o instalador faz

- instala/verifica `uv`/`uvx`;
- executa o preflight offline do MCP;
- faz backup de `~/.codex/config.toml`;
- adiciona o servidor `gemini` com perfil `core`;
- tenta instalar o skill `gemini-web-mcp` para Codex, se `npx` estiver disponível;
- deixa o Codex pronto para carregar a sessão do Gemini pelo Chrome.

O perfil `core` inclui `gemini_generate_media`, com `media_type="video"`, além de upload/análise de arquivos e ferramentas de diagnóstico.

## Instalação

No Windows, execute:

`INSTALAR_GEMINI_MCP.bat`

Depois feche completamente o Codex e abra novamente.

Mantenha a conta desejada já logada em `https://gemini.google.com` no Chrome.

No Codex, envie:

```text
Use o MCP gemini. Primeiro liste os perfis de cookie do Chrome sem expor valores secretos. Depois carregue o perfil do Chrome que estiver logado no Gemini. Em seguida rode gemini_get_cookie_status e gemini_doctor. Se a autenticacao estiver valida, faca um teste temporario respondendo exatamente: Gemini MCP conectado. Nao leia meu historico e nao exclua nada.
```

Se houver mais de um perfil do Chrome, escolha explicitamente o perfil correto.

## Produção do vídeo STEP

Após o teste de conexão, abra `PROMPT_CODEX_VIDEO_STEP.md` e envie o conteúdo ao Codex junto com a pasta que contém:

- logo oficial da STEP;
- vídeos reais de referência;
- fotos opcionais.

O fluxo foi desenhado para produzir um vídeo final de 50–60 segundos para painel 2 m x 1 m, misturando os melhores trechos reais com cenas geradas no Veo quando necessário.

## Arquivo alterado no PC

O instalador altera apenas a configuração global do Codex em:

`%USERPROFILE%\.codex\config.toml`

Antes da alteração, uma cópia de segurança com timestamp é criada automaticamente.

## Credenciais

Não salve cookies do Gemini no GitHub e não os cole em issues, commits, chats públicos ou logs. O fluxo recomendado é deixar o MCP localizar/carregar localmente a sessão do Chrome sem expor os valores dos cookies.
