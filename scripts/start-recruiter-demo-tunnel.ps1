param(
    [Parameter(Mandatory = $true)]
    [string]$FrontendOrigin,

    [int]$Port = 8000,

    [string[]]$AllowedEmails = @()
)

$ErrorActionPreference = "Stop"

try {
    $frontendUri = [System.Uri]$FrontendOrigin
} catch {
    Write-Host "FrontendOrigin must be a valid origin, for example https://demo.example.com" -ForegroundColor Red
    exit 1
}

if (
    $frontendUri.Scheme -ne "https" -or
    [string]::IsNullOrWhiteSpace($frontendUri.Host) -or
    $frontendUri.AbsolutePath -ne "/" -or
    $frontendUri.Query -or
    $frontendUri.Fragment -or
    $frontendUri.UserInfo
) {
    Write-Host "Pass only the HTTPS origin of the deployed frontend, without a path." -ForegroundColor Red
    exit 1
}

$frontendOriginValue = $frontendUri.GetLeftPart([System.UriPartial]::Authority).TrimEnd("/")
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$gitCommand = Get-Command git -ErrorAction SilentlyContinue
if (-not $gitCommand) {
    Write-Host "Git was not found on PATH. Clone the repository and install Git before starting the demo." -ForegroundColor Red
    exit 1
}
$currentBranch = (& $gitCommand.Source -C $repoRoot branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $currentBranch -ne "demo") {
    Write-Host "Safety stop: this launcher only runs from the Backend demo branch. Current branch: $currentBranch" -ForegroundColor Red
    exit 1
}

$cloudflaredCommand = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cloudflaredCommand) {
    Write-Host "cloudflared is not installed. Install it with: winget install --id Cloudflare.cloudflared --exact" -ForegroundColor Red
    Write-Host "Open a new PowerShell window after installation, then run this script again."
    exit 1
}

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
    Write-Host "Python 3.10 or newer was not found on PATH." -ForegroundColor Red
    exit 1
}

$pythonVersionText = & $pythonCommand.Source --version 2>&1
if ($pythonVersionText -notmatch "Python\s+(\d+)\.(\d+)") {
    Write-Host "Could not read the installed Python version." -ForegroundColor Red
    exit 1
}
$pythonMajor = [int]$Matches[1]
$pythonMinor = [int]$Matches[2]
if ($pythonMajor -lt 3 -or ($pythonMajor -eq 3 -and $pythonMinor -lt 10)) {
    Write-Host "Python 3.10 or newer is required. Found: $pythonVersionText" -ForegroundColor Red
    exit 1
}

$venvPath = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Creating the isolated demo Python environment..."
    & $pythonCommand.Source -m venv $venvPath
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the Python virtual environment."
    }
}

Write-Host "Checking the standalone demo API dependencies..."
& $venvPython -m pip install --disable-pip-version-check fastapi "uvicorn[standard]" pydantic python-multipart
if ($LASTEXITCODE -ne 0) {
    throw "Could not install the standalone demo API dependencies."
}

# Refuse to take over an existing service on the selected port.
$portProbe = [System.Net.Sockets.TcpClient]::new()
try {
    $portProbe.Connect("127.0.0.1", $Port)
    Write-Host "Port $Port is already accepting connections. Stop that service or choose another port with -Port." -ForegroundColor Red
    exit 1
} catch {
    if ($portProbe.Connected) { throw }
} finally {
    $portProbe.Dispose()
}

$previousAllowedOrigins = $env:FRAMEFLUX_DEMO_ALLOWED_ORIGINS
$env:FRAMEFLUX_DEMO_ALLOWED_ORIGINS = $frontendOriginValue

$logDirectory = Join-Path $env:TEMP "frameflux-demo-tunnel"
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
$stdoutLog = Join-Path $logDirectory "api.stdout.log"
$stderrLog = Join-Path $logDirectory "api.stderr.log"
Remove-Item $stdoutLog, $stderrLog -Force -ErrorAction SilentlyContinue

$apiProcess = $null

try {
    Write-Host ""
    Write-Host "Starting the FrameFlux demo API on 127.0.0.1:$Port..."
    $uvicornArgs = @("-m", "uvicorn", "app.demo.main:app", "--host", "127.0.0.1", "--port", "$Port", "--no-access-log")
    $apiProcess = Start-Process -FilePath $venvPython -ArgumentList $uvicornArgs -WorkingDirectory $repoRoot -WindowStyle Hidden -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog -PassThru

    $apiReady = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        if ($apiProcess.HasExited) { break }
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/demo/runtime" -TimeoutSec 2
            if ($health.mode -eq "in-memory" -and $health.production_isolated -eq $true) {
                $apiReady = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 750
        }
    }

    if (-not $apiReady) {
        if (Test-Path $stderrLog) {
            Write-Host (Get-Content $stderrLog -Raw) -ForegroundColor DarkYellow
        }
        throw "The demo API did not become healthy. Check logs in $logDirectory"
    }

    Write-Host "API health check passed: http://127.0.0.1:$Port/demo/runtime" -ForegroundColor Green
    Write-Host "CORS is restricted to: $frontendOriginValue"
    Write-Host ""
    Write-Host "Starting a temporary Cloudflare Quick Tunnel..."
    Write-Host "Copy the https://....trycloudflare.com URL printed by cloudflared."
    Write-Host "Then open this frontend link (replace the placeholder with the tunnel URL):"
    Write-Host "$frontendOriginValue/?demoBackend=<URL-ENCODED-TRY-CLOUDFLARE-URL>" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Keep this window open. Press Ctrl+C to stop the tunnel and local API."
    Write-Host "The API stores temporary in-memory demo state; do not upload private media." -ForegroundColor Yellow

    $tunnelArgs = @("tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:$Port")
    Write-Host "WARNING: anyone who obtains the temporary tunnel URL can reach this demo API." -ForegroundColor Yellow
    & $cloudflaredCommand.Source @tunnelArgs
} finally {
    if ($apiProcess -and -not $apiProcess.HasExited) {
        Write-Host ""
        Write-Host "Stopping the local FrameFlux demo API..."
        Stop-Process -Id $apiProcess.Id -Force -ErrorAction SilentlyContinue
    }

    if ($null -eq $previousAllowedOrigins) {
        Remove-Item Env:FRAMEFLUX_DEMO_ALLOWED_ORIGINS -ErrorAction SilentlyContinue
    } else {
        $env:FRAMEFLUX_DEMO_ALLOWED_ORIGINS = $previousAllowedOrigins
    }
}
