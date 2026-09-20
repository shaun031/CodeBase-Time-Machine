param(
    [string]$BackendUrl = 'http://127.0.0.1:8000',
    [string]$OllamaUrl = 'http://127.0.0.1:11434'
)

$ErrorActionPreference = 'Continue'
$projectRoot = Split-Path $PSScriptRoot -Parent
$checks = [System.Collections.Generic.List[object]]::new()

function Add-Check([string]$Name, [bool]$Passed, [string]$Guidance) {
    $checks.Add([pscustomobject]@{ Check = $Name; Status = $(if ($Passed) { 'Ready' } else { 'Needs attention' }); Guidance = $Guidance })
}

function Has-Command([string]$Command) { return $null -ne (Get-Command $Command -ErrorAction SilentlyContinue) }

Add-Check 'Python' (Has-Command 'python') 'Install Python 3.11+ or activate backend\.venv.'
Add-Check 'Node.js' (Has-Command 'node') 'Install the current Node.js LTS release.'
Add-Check 'Git' (Has-Command 'git') 'Install Git for Windows and reopen the terminal.'

$backendHealthy = $false
try { $backendHealthy = (Invoke-RestMethod "$BackendUrl/api/health" -TimeoutSec 3).status -eq 'ok' } catch {}
Add-Check 'Backend health' $backendHealthy "Start it with: cd '$projectRoot\backend'; npm run dev"

$ollamaReachable = $false
$models = @()
try {
    $models = (Invoke-RestMethod "$OllamaUrl/api/tags" -TimeoutSec 3).models.name
    $ollamaReachable = $true
} catch {}
Add-Check 'Ollama service' $ollamaReachable 'Run: ollama serve'

if ($ollamaReachable) {
    $envPath = Join-Path $projectRoot 'backend\.env'
    $embeddingModel = 'all-minilm:latest'
    $llmModel = 'qwen3:4b'
    if (Test-Path $envPath) {
        foreach ($line in Get-Content $envPath) {
            if ($line -match '^OLLAMA_EMBEDDING_MODEL=(.+)$') { $embeddingModel = $Matches[1].Trim() }
            if ($line -match '^OLLAMA_LLM_MODEL=(.+)$') { $llmModel = $Matches[1].Trim() }
        }
    }
    Add-Check "Embedding model ($embeddingModel)" ($models -contains $embeddingModel) "Run: ollama pull $embeddingModel"
    Add-Check "LLM model ($llmModel)" ($models -contains $llmModel) "Run: ollama pull $llmModel"
}

$checks | Format-Table -AutoSize
if ($checks.Status -contains 'Needs attention') { exit 1 }
