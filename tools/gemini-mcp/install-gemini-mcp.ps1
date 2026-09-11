$ErrorActionPreference = 'Stop'

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machine;$user"
}

Write-Host "STEP - Instalador Gemini Web MCP para Codex" -ForegroundColor Green
Write-Host "Este instalador configura o Gemini Web MCP em ~/.codex/config.toml." -ForegroundColor DarkGray
Write-Host "O projeto usado faz engenharia reversa do Gemini Web e pode envolver risco de conta/termos do Google." -ForegroundColor Yellow
Write-Host "Recomendado: usar uma conta Google dedicada para este acesso." -ForegroundColor Yellow

Write-Step "Verificando uv/uvx"
if (-not (Get-Command uvx -ErrorAction SilentlyContinue)) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "uvx nao encontrado. Instalando uv via winget..."
        winget install --id astral-sh.uv -e --accept-source-agreements --accept-package-agreements
        Refresh-Path
    }
    elseif (Get-Command py -ErrorAction SilentlyContinue) {
        Write-Host "winget nao encontrado. Instalando uv com Python..."
        py -m pip install --user uv
        Refresh-Path
    }
    elseif (Get-Command python -ErrorAction SilentlyContinue) {
        Write-Host "winget nao encontrado. Instalando uv com Python..."
        python -m pip install --user uv
        Refresh-Path
    }
    else {
        throw "Nao encontrei winget nem Python para instalar o uv. Instale o uv e execute novamente."
    }
}

if (-not (Get-Command uvx -ErrorAction SilentlyContinue)) {
    $candidate = Join-Path $HOME '.local\bin\uvx.exe'
    if (Test-Path $candidate) {
        $env:Path = "$(Split-Path $candidate);$env:Path"
    }
}

if (-not (Get-Command uvx -ErrorAction SilentlyContinue)) {
    throw "uvx ainda nao esta disponivel no PATH. Feche e abra o terminal e execute novamente."
}

Write-Host "uvx encontrado: $((Get-Command uvx).Source)" -ForegroundColor Green

Write-Step "Executando teste offline do servidor MCP"
& uvx --from 'git+https://github.com/Luckycat133/gemini-web-mcp@main' gemini-mcp-onboarding
if ($LASTEXITCODE -ne 0) {
    throw "O preflight offline do Gemini MCP falhou."
}

Write-Step "Configurando Codex"
$codexDir = Join-Path $HOME '.codex'
$configPath = Join-Path $codexDir 'config.toml'
New-Item -ItemType Directory -Path $codexDir -Force | Out-Null

$current = ''
if (Test-Path $configPath) {
    $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    Copy-Item $configPath "$configPath.backup-$timestamp" -Force
    Write-Host "Backup criado: $configPath.backup-$timestamp" -ForegroundColor DarkGray
    $current = Get-Content -Path $configPath -Raw
}

$pattern = '(?s)\r?\n?# BEGIN STEP GEMINI MCP.*?# END STEP GEMINI MCP\r?\n?'
$current = [regex]::Replace($current, $pattern, "`r`n")

$block = @'
# BEGIN STEP GEMINI MCP
[mcp_servers.gemini]
command = "uvx"
args = [
  "--from",
  "git+https://github.com/Luckycat133/gemini-web-mcp@main",
  "gemini-mcp-server",
]
startup_timeout_sec = 60
tool_timeout_sec = 720

[mcp_servers.gemini.env]
GEMINI_TOOLS = "core"
GEMINI_AUTO_REFRESH = "false"
# END STEP GEMINI MCP
'@

$newContent = ($current.TrimEnd() + "`r`n`r`n" + $block.Trim() + "`r`n")
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($configPath, $newContent, $utf8NoBom)
Write-Host "Codex configurado em: $configPath" -ForegroundColor Green

Write-Step "Instalando skill do Gemini MCP no Codex (opcional, mas recomendado)"
if (Get-Command npx -ErrorAction SilentlyContinue) {
    & npx --yes skills@1.5.21 add 'https://github.com/Luckycat133/gemini-web-mcp' --skill gemini-web-mcp --agent codex --copy --yes
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Skill instalada." -ForegroundColor Green
    }
    else {
        Write-Host "A skill nao foi instalada, mas o MCP principal ja esta configurado." -ForegroundColor Yellow
    }
}
else {
    Write-Host "npx/Node.js nao encontrado. Pulei a skill. O MCP principal funciona sem ela." -ForegroundColor Yellow
}

Write-Step "Instalacao concluida"
Write-Host "1. Feche COMPLETAMENTE o Codex e abra novamente." -ForegroundColor White
Write-Host "2. Confirme que voce esta logado em https://gemini.google.com no Chrome." -ForegroundColor White
Write-Host "3. No Codex, cole o prompt abaixo para carregar a sessao do Gemini do Chrome:" -ForegroundColor White
Write-Host "" 
Write-Host 'Use o MCP gemini. Primeiro liste os perfis de cookie do Chrome sem expor valores secretos. Depois carregue o perfil do Chrome que estiver logado no Gemini. Em seguida rode gemini_get_cookie_status e gemini_doctor. Se a autenticacao estiver valida, faca um teste temporario respondendo exatamente: Gemini MCP conectado. Nao leia meu historico e nao exclua nada.' -ForegroundColor Green
Write-Host ""
Write-Host "Depois que esse teste passar, o perfil core disponibiliza gemini_generate_media, inclusive media_type=video." -ForegroundColor Cyan
