# FLUXAA Port — fonctions communes des lanceurs Windows (installation locale de démonstration).
# Chargé par demarrer.ps1, codes.ps1, arreter.ps1 et reinitialiser.ps1. Windows PowerShell 5.1.
# Encodage du fichier : UTF-8 avec BOM (nécessaire à PowerShell 5.1 pour les caractères accentués).

$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$script:Racine = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$script:Deploy = Join-Path $script:Racine 'deploy'
$script:EnvFile = Join-Path $script:Deploy '.env'
$script:PortsFile = Join-Path $script:Deploy 'docker-compose.ports.yml'
$script:Comptes = Join-Path $script:Racine 'COMPTES-DEMO.txt'
$script:VersionFile = Join-Path $PSScriptRoot 'version-installee.txt'
$script:MotDePasseDemo = 'Demo-Fluxaa-2026'
$script:Docker = $null

# ----------------------------------------------------------------------------------- affichage
function Write-Titre([string]$texte) {
    Write-Host ''
    Write-Host ('=' * 78) -ForegroundColor DarkCyan
    Write-Host "  $texte" -ForegroundColor Cyan
    Write-Host ('=' * 78) -ForegroundColor DarkCyan
}

function Write-Etape([string]$texte) {
    Write-Host ''
    Write-Host "> $texte" -ForegroundColor Yellow
}

function Write-Ok([string]$texte) { Write-Host "  OK  $texte" -ForegroundColor Green }
function Write-Alerte([string]$texte) { Write-Host "  !!  $texte" -ForegroundColor DarkYellow }
function Write-Echec([string]$texte) { Write-Host "  XX  $texte" -ForegroundColor Red }

function Pause-Fin {
    Write-Host ''
    $null = Read-Host "Appuyez sur Entrée pour fermer cette fenêtre"
}

# ------------------------------------------------------------------------------------- docker
function Find-Docker {
    $commande = Get-Command 'docker.exe' -ErrorAction SilentlyContinue
    if ($commande) { return $commande.Source }
    $candidats = @(
        (Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Docker\Docker\resources\bin\docker.exe')
    )
    foreach ($chemin in $candidats) {
        if (Test-Path $chemin) { return $chemin }
    }
    return $null
}

function Find-DockerDesktop {
    $candidats = @(
        (Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Docker\Docker\Docker Desktop.exe')
    )
    foreach ($chemin in $candidats) {
        if (Test-Path $chemin) { return $chemin }
    }
    return $null
}

function Test-DockerPret {
    if (-not $script:Docker) { return $false }
    try {
        $null = & $script:Docker info --format '{{.ServerVersion}}' 2>$null
    } catch {
        return $false
    }
    return ($LASTEXITCODE -eq 0)
}

function Wait-Docker([int]$secondes) {
    $fin = (Get-Date).AddSeconds($secondes)
    while ((Get-Date) -lt $fin) {
        if (Test-DockerPret) { Write-Host ''; return $true }
        Write-Host -NoNewline '.'
        Start-Sleep -Seconds 5
    }
    Write-Host ''
    return $false
}

# Trouve Docker et, s'il faut, lance Docker Desktop. Retourne $true quand le moteur répond.
function Initialize-Docker {
    $script:Docker = Find-Docker
    if (-not $script:Docker) {
        Write-Echec "Docker Desktop n'est pas installé sur cet ordinateur."
        Write-Host "  La plateforme tourne dans Docker Desktop. Pour l'installer :"
        Write-Host "  1. Sur la page qui s'ouvre, cliquez sur « Download for Windows » et lancez l'installateur."
        Write-Host "  2. Redémarrez l'ordinateur s'il le demande, ouvrez Docker Desktop une première fois et acceptez les conditions."
        Write-Host "  3. Double-cliquez de nouveau sur DEMARRER.cmd."
        Start-Process 'https://www.docker.com/products/docker-desktop/'
        return $false
    }
    if (-not (Test-DockerPret)) {
        Write-Etape "Démarrage de Docker Desktop (jusqu'à quelques minutes)…"
        $application = Find-DockerDesktop
        if ($application) {
            Start-Process -FilePath $application | Out-Null
        } else {
            Write-Alerte "Docker Desktop introuvable : ouvrez-le vous-même depuis le menu Démarrer, l'attente continue ici."
        }
        Write-Host "  Si Docker Desktop affiche une fenêtre (conditions d'utilisation, connexion, mise à jour), répondez-y."
        if (-not (Wait-Docker 300)) {
            Write-Echec "Docker ne répond pas après cinq minutes."
            Write-Host "  Ouvrez Docker Desktop, attendez que son icône indique « Engine running », puis relancez DEMARRER.cmd."
            Write-Host "  Au premier lancement, Docker Desktop peut demander d'activer WSL 2 : suivez ses indications et redémarrez."
            return $false
        }
    }
    $null = & $script:Docker compose version 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Echec "Cette version de Docker ne connaît pas « docker compose » : mettez Docker Desktop à jour."
        return $false
    }
    return $true
}

# Fichiers Compose de l'installation locale (chemins relatifs : le dossier courant est deploy/).
function Get-ComposeFiles {
    $fichiers = @('-f', 'docker-compose.yml', '-f', 'docker-compose.local.yml')
    if (Test-Path $script:PortsFile) { $fichiers += @('-f', 'docker-compose.ports.yml') }
    return $fichiers
}

# Lance « docker compose <arguments> » dans deploy/ ; la sortie s'affiche ; retourne le code de sortie.
function Invoke-Compose([string[]]$arguments) {
    $fichiers = Get-ComposeFiles
    & $script:Docker compose $fichiers $arguments | Out-Host
    return $LASTEXITCODE
}

# Même chose, mais la sortie est capturée (texte) ; le code de sortie est dans $script:DernierCode.
function Invoke-ComposeCapture([string[]]$arguments) {
    $fichiers = Get-ComposeFiles
    $sortie = & $script:Docker compose $fichiers $arguments 2>&1 | ForEach-Object { "$_" }
    $script:DernierCode = $LASTEXITCODE
    return $sortie
}

# --------------------------------------------------------------------------------------- .env
function Read-EnvValue([string]$nom) {
    if (-not (Test-Path $script:EnvFile)) { return $null }
    foreach ($ligne in Get-Content $script:EnvFile) {
        if ($ligne -match ('^\s*' + [regex]::Escape($nom) + '\s*=\s*(.*)$')) {
            return $Matches[1].Trim().Trim('"')
        }
    }
    return $null
}

# Port HTTPS de l'installation locale, lu dans FLUXAA_SITE_URL (443 par défaut).
function Get-PortLocal {
    $url = Read-EnvValue 'FLUXAA_SITE_URL'
    if ($url -and $url -match ':(\d+)/?$') { return [int]$Matches[1] }
    return 443
}

function Get-UrlLocale {
    $port = Get-PortLocal
    if ($port -eq 443) { return 'https://localhost/' }
    return "https://localhost:$port/"
}

# Les lanceurs ne gèrent qu'une installation locale de démonstration (DOMAIN=localhost).
function Test-InstallationLocale {
    if (-not (Test-Path $script:EnvFile)) { return $true }
    $domaine = Read-EnvValue 'DOMAIN'
    return ($domaine -eq 'localhost')
}

function Write-FichierSansBom([string]$chemin, [string]$contenu) {
    $contenu = $contenu -replace "`r`n", "`n"
    $encodage = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($chemin, $contenu, $encodage)
}

function Write-FichierAvecBom([string]$chemin, [string]$contenu) {
    $encodage = New-Object System.Text.UTF8Encoding($true)
    [System.IO.File]::WriteAllText($chemin, $contenu, $encodage)
}
