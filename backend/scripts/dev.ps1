$ErrorActionPreference = 'Stop'
$backendDirectory = Split-Path $PSScriptRoot -Parent
$projectRoot = Split-Path $backendDirectory -Parent
$environmentFile = Join-Path $projectRoot '.env'
$environmentExample = Join-Path $projectRoot '.env.example'

function Read-EnvironmentValue([string]$Name) {
    $line = Get-Content -LiteralPath $environmentFile | Where-Object {
        $_ -match "^$([regex]::Escape($Name))="
    } | Select-Object -First 1
    if (-not $line) { return $null }
    $value = $line.Substring($Name.Length + 1).Trim()
    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
        ($value.StartsWith("'") -and $value.EndsWith("'"))) {
        return $value.Substring(1, $value.Length - 2)
    }
    return $value
}

function Test-LocalPort([int]$Port) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $pending = $client.ConnectAsync('127.0.0.1', $Port)
        return $pending.Wait(300) -and $client.Connected
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Test-DockerEngine {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { return $false }
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'SilentlyContinue'
        & docker info *> $null
        return $LASTEXITCODE -eq 0
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

if (-not (Test-Path -LiteralPath $environmentFile)) {
    Copy-Item -LiteralPath $environmentExample -Destination $environmentFile
    Write-Host 'Created .env from .env.example.'
}

$dockerReady = Test-DockerEngine
if ($dockerReady) {
    $runningServices = @(& docker compose --project-directory $projectRoot ps --services --filter status=running 2>$null)
    if ($runningServices -contains 'backend' -or $runningServices -contains 'worker') {
        Write-Host 'Stopping Docker backend services so the native server can use port 8000...'
        & docker compose --project-directory $projectRoot stop backend worker
        if ($LASTEXITCODE -ne 0) { throw 'Could not stop the Docker backend services.' }
    }
}

if (Test-LocalPort 8000) {
    throw 'Port 8000 is already in use. Stop the existing backend process and retry.'
}

$databaseUrl = Read-EnvironmentValue 'DATABASE_URL'
if (-not $databaseUrl) { throw 'DATABASE_URL is missing from the root .env file.' }
$databaseUrl = $databaseUrl -replace '@postgres:', '@127.0.0.1:'
$databaseUrl = $databaseUrl -replace '@localhost:', '@127.0.0.1:'
$env:DATABASE_URL = $databaseUrl
$databaseUri = [Uri]($databaseUrl -replace '^postgresql\+psycopg', 'postgresql')
$databasePort = if ($databaseUri.IsDefaultPort) { 5432 } else { $databaseUri.Port }
$projectPostgresData = Join-Path $projectRoot 'data/postgres-dev'
$nativePgCtl = 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe'
$env:TASK_EXECUTION_MODE = 'local'
$env:REPOSITORY_STORAGE_PATH = (Join-Path $projectRoot 'data/repositories')
$ollamaUrl = Read-EnvironmentValue 'OLLAMA_BASE_URL'
if ($ollamaUrl) {
    $env:OLLAMA_BASE_URL = $ollamaUrl -replace 'host\.docker\.internal', '127.0.0.1'
}
$env:PYTHONUNBUFFERED = '1'

if (-not (Test-LocalPort $databasePort)) {
    if (
        $databaseUri.Host -eq '127.0.0.1' -and
        (Test-Path -LiteralPath (Join-Path $projectPostgresData 'PG_VERSION')) -and
        (Test-Path -LiteralPath $nativePgCtl)
    ) {
        Write-Host "Starting project PostgreSQL on port $databasePort..."
        $postgresLog = Join-Path $projectPostgresData 'server.log'
        & $nativePgCtl start -D $projectPostgresData -l $postgresLog `
            -o "-p $databasePort -h 127.0.0.1" -w
        if ($LASTEXITCODE -ne 0) { throw 'Project PostgreSQL could not be started.' }
    } elseif (-not $dockerReady -or $databasePort -ne 5432) {
        throw "PostgreSQL is unavailable on configured port $databasePort."
    }
}

if (-not (Test-LocalPort $databasePort)) {
    Write-Host 'Starting PostgreSQL...'
    & docker compose --project-directory $projectRoot up -d --wait postgres
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL could not be started.' }
}

$python = Join-Path $backendDirectory '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    Write-Host 'Creating the backend virtual environment...'
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv (Join-Path $backendDirectory '.venv')
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv (Join-Path $backendDirectory '.venv')
    } else {
        throw 'Python 3.12 or newer is required.'
    }
    if ($LASTEXITCODE -ne 0) { throw 'The Python virtual environment could not be created.' }
}

& $python -c "import sys; assert sys.version_info >= (3, 12)"
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 or newer is required.' }

& $python -c "import alembic, fastapi, httpx, pgvector, psycopg, sqlalchemy, tree_sitter, tree_sitter_language_pack, uvicorn" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Installing locked backend dependencies...'
    & $python -m pip install --disable-pip-version-check -r (Join-Path $backendDirectory 'requirements.lock')
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
    & $python -m pip install --disable-pip-version-check --no-deps -e "${backendDirectory}[dev]"
    if ($LASTEXITCODE -ne 0) { throw 'Backend package installation failed.' }
}

Push-Location $backendDirectory
try {
    Write-Host 'Applying database migrations...'
    & $python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Database migrations failed.' }
    Write-Host 'Starting CodeChronicle backend at http://127.0.0.1:8000'
    & $python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
    if ($LASTEXITCODE -ne 0) { throw "The backend exited with code $LASTEXITCODE." }
} finally {
    Pop-Location
}
