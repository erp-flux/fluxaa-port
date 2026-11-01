# FLUXAA Port — démarrage d'une installation locale de démonstration sous Windows (DEMARRER.cmd).
# Première fois : configuration et secrets générés, construction de l'image, démarrage, données de
# démonstration des deux ports, certificat local reconnu par Windows, ouverture du navigateur.
# Les fois suivantes : démarrage et ouverture du navigateur. Les données sont conservées.
# Windows PowerShell 5.1. Encodage du fichier : UTF-8 avec BOM.

. (Join-Path $PSScriptRoot 'commun.ps1')
$script:Code = 1

function New-RandomBytes([int]$nombre) {
    $octets = New-Object byte[] $nombre
    $generateur = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $generateur.GetBytes($octets)
    return ,$octets
}

function New-Hex([int]$nombre) {
    return ((New-RandomBytes $nombre) | ForEach-Object { $_.ToString('x2') }) -join ''
}

function New-UrlSafe([int]$nombre) {
    return ([Convert]::ToBase64String((New-RandomBytes $nombre))).Replace('+', '-').Replace('/', '_').TrimEnd('=')
}

# Clé Fernet : 32 octets aléatoires en base64 « URL-safe », avec son remplissage « = ».
function New-FernetKey {
    return ([Convert]::ToBase64String((New-RandomBytes 32))).Replace('+', '-').Replace('/', '_')
}

function Test-PortLibre([int]$port) {
    try {
        $ecoute = New-Object System.Net.Sockets.TcpListener -ArgumentList ([System.Net.IPAddress]::Any), $port
        $ecoute.Start()
        $ecoute.Stop()
        return $true
    } catch {
        return $false
    }
}

# Ports publiés par le frontal : 443/80 si libres, sinon 8443/8080, sinon 9443/9090.
function Select-Ports {
    foreach ($paire in @(@(443, 80), @(8443, 8080), @(9443, 9090))) {
        if ((Test-PortLibre $paire[0]) -and (Test-PortLibre $paire[1])) { return $paire }
    }
    return @(443, 80)
}

function New-EnvLocal([int]$portHttps) {
    $hote = 'localhost'
    if ($portHttps -ne 443) { $hote = "localhost:$portHttps" }
    $date = Get-Date -Format 'yyyy-MM-dd HH:mm'
    $secretDjango = New-UrlSafe 50
    $cleScellement = New-UrlSafe 50
    $cleN4 = New-FernetKey
    $mdpPostgres = New-Hex 24
    $mdpOwner = New-Hex 24
    $mdpApp = New-Hex 24
    $mdpSecure = New-Hex 24
    $contenu = @"
# FLUXAA Port — configuration d'une installation LOCALE DE DÉMONSTRATION, créée par DEMARRER.cmd le $date.
# Adresse : https://$hote/ — données fictives ; les courriels sont écrits dans le journal du conteneur
# web (aucun envoi) ; aucun SMS. Pour une installation réelle : .env.example et docs/DEPLOIEMENT.md.
# Gardez une copie de ce fichier : sans ces clés, les sceaux et les codes d'authentification de cette
# installation deviennent invérifiables.
DOMAIN=localhost
DJANGO_ALLOWED_HOSTS=localhost
DJANGO_CSRF_TRUSTED_ORIGINS=https://$hote
FLUXAA_SITE_URL=https://$hote
DJANGO_HSTS_SECONDS=0
DJANGO_SECRET_KEY=$secretDjango
FLUXAA_SIGNING_KEY=$cleScellement
FLUXAA_N4_KEYS=$cleN4
POSTGRES_PASSWORD=$mdpPostgres
FLUXAA_OWNER_PASSWORD=$mdpOwner
FLUXAA_APP_PASSWORD=$mdpApp
FLUXAA_SECURE_APP_PASSWORD=$mdpSecure
DATABASE_URL=postgres://fluxaa_app:${mdpApp}@db:5432/fluxaa
DATABASE_OWNER_URL=postgres://fluxaa_owner:${mdpOwner}@db:5432/fluxaa
SECURE_DATABASE_URL=postgres://fluxaa_secure_app:${mdpSecure}@db:5432/fluxaa_secure
SECURE_DATABASE_OWNER_URL=postgres://fluxaa_owner:${mdpOwner}@db:5432/fluxaa_secure
FLUXAA_TIMESTAMP_PROVIDER=local
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
DEFAULT_FROM_EMAIL="FLUXAA Port <no-reply@localhost>"
FLUXAA_SMS_BACKEND=console
FLUXAA_MFA_ENFORCED=1
FLUXAA_AI_ENABLED=0
LOG_LEVEL=INFO
BACKUP_HOST_DIR=./backups
BACKUP_RETENTION_DAYS=30
"@
    Write-FichierSansBom $script:EnvFile $contenu
}

function Write-PortsOverride([int]$portHttps, [int]$portHttp) {
    if ($portHttps -eq 443) { return }
    $contenu = @"
# Écrit par DEMARRER.cmd : les ports 443/80 étaient occupés sur cet ordinateur.
services:
  caddy:
    ports: !override
      - "${portHttps}:443"
      - "${portHttp}:80"
"@
    Write-FichierSansBom $script:PortsFile $contenu
}

function Wait-WebPret([int]$secondes) {
    $fin = (Get-Date).AddSeconds($secondes)
    while ((Get-Date) -lt $fin) {
        $etat = & $script:Docker inspect -f '{{.State.Health.Status}}' 'fluxaa-web-1' 2>$null
        if ($LASTEXITCODE -eq 0) {
            $etat = "$etat".Trim()
            if ($etat -eq 'healthy') { Write-Host ''; return $true }
            $enMarche = & $script:Docker inspect -f '{{.State.Running}}' 'fluxaa-web-1' 2>$null
            if ("$enMarche".Trim() -ne 'true') { Write-Host ''; return $false }
        }
        Write-Host -NoNewline '.'
        Start-Sleep -Seconds 5
    }
    Write-Host ''
    return $false
}

# 0 : données de démonstration déjà présentes ; 3 : absentes ; autre : impossible de le savoir.
function Get-EtatDemo {
    $programme = "from apps.core.models import User; import sys; sys.exit(0 if User.objects.filter(email__endswith='@demo.fluxaa.test').exists() else 3)"
    $null = Invoke-ComposeCapture @('exec', '-T', 'web', 'python', 'manage.py', 'shell', '-c', $programme)
    return $script:DernierCode
}

function Load-Demo {
    $lignes = @()
    foreach ($port in @('TGLFW', 'SLFNA')) {
        Write-Host "  Port $port…"
        $sortie = Invoke-ComposeCapture @('exec', '-T', 'web', 'python', 'manage.py', 'load_demo', '--port', $port, '--password', $script:MotDePasseDemo)
        $journal = Join-Path $PSScriptRoot "load_demo-$port.log"
        Write-FichierSansBom $journal ($sortie -join "`n")
        if ($script:DernierCode -ne 0) {
            Write-Echec "Le chargement des données de démonstration de $port a échoué (détail : deploy\windows\load_demo-$port.log)."
            return $null
        }
        foreach ($ligne in $sortie) {
            if ($ligne -match '^\s*([A-Z,]{3,})\s+(\S+@\S+?)\s*(?:TOTP\s+([A-Z2-7]+))?\s*$') {
                $role = $Matches[1]
                $compte = $Matches[2]
                $cle = ''
                if ($Matches[3]) { $cle = $Matches[3] }
                $lignes += ('{0,-8}{1,-40}{2}' -f $role, $compte, $cle)
            }
            elseif ($ligne -match '^Access without account.*?: (http\S+)\s+or code (\S+)') {
                $lignes += ('{0,-8}{1}  (code {2})' -f 'LIEN', $Matches[1], $Matches[2])
            }
        }
    }
    return $lignes
}

function Write-Comptes([string[]]$lignes) {
    $texte = @"
FLUXAA Port — comptes de démonstration de cette installation locale (données fictives)
=======================================================================================

Adresse : $(Get-UrlLocale)
Mot de passe de tous les comptes : $script:MotDePasseDemo

Les comptes « tglfw » sont ceux de Lomé (interface en français), les comptes « slfna » ceux de
Freetown (interface en anglais). Les rôles qui décident (CAP capitainerie, APO autorité portuaire,
ADM douanes-santé, SUR sûreté) et l'administrateur du port (DIR) demandent, après le mot de passe,
un code à 6 chiffres : double-cliquez sur CODES-DEMO.cmd pour l'obtenir, ou saisissez la clé TOTP
ci-dessous dans une application d'authentification (Google Authenticator, Microsoft Authenticator…).
Accès capitaine (sans compte) : l'agence le délivre depuis l'onglet « Parties » d'une escale.
Accès d'une partie sans compte : la ligne « LIEN » ci-dessous est le lien du laboratoire indépendant
convoqué sur l'escale STS (nom demandé à la première ouverture) ; chaque autre partie sans compte reçoit
le sien par courriel à la déclaration.

Rôle    Compte                                  Clé TOTP
$($lignes -join "`n")

Ce fichier contient des secrets : ne le diffusez pas. Le guide par rôle et la démonstration en dix
minutes sont dans docs/GUIDE_UTILISATEUR.md.
"@
    Write-FichierAvecBom $script:Comptes $texte
}

function Install-CertificatLocal {
    $fichier = Join-Path $env:TEMP 'fluxaa-caddy-root.crt'
    if (Test-Path $fichier) { Remove-Item $fichier -Force -ErrorAction SilentlyContinue }
    $trouve = $false
    for ($essai = 0; $essai -lt 12; $essai++) {
        $null = Invoke-ComposeCapture @('cp', 'caddy:/data/caddy/pki/authorities/local/root.crt', $fichier)
        if (($script:DernierCode -eq 0) -and (Test-Path $fichier)) { $trouve = $true; break }
        Start-Sleep -Seconds 5
    }
    if (-not $trouve) {
        Write-Alerte "Certificat local non récupéré : le navigateur affichera un avertissement, que vous pouvez ignorer (« Paramètres avancés » puis « Continuer vers localhost »)."
        return
    }
    try {
        $certificat = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 -ArgumentList $fichier
        $magasin = New-Object System.Security.Cryptography.X509Certificates.X509Store -ArgumentList 'Root', 'CurrentUser'
        $magasin.Open('ReadOnly')
        $deja = $magasin.Certificates.Find('FindByThumbprint', $certificat.Thumbprint, $false).Count -gt 0
        $magasin.Close()
        if ($deja) {
            Write-Ok "Le certificat de cette installation est déjà reconnu par Windows."
            return
        }
        Write-Host "  Windows va demander si vous reconnaissez le certificat de cette installation (« Caddy Local Authority ») :"
        Write-Host "  répondez Oui pour que le navigateur affiche le cadenas. Sinon il affichera un avertissement, que vous pouvez ignorer."
        $null = Import-Certificate -FilePath $fichier -CertStoreLocation 'Cert:\CurrentUser\Root' -ErrorAction Stop
        Write-Ok "Certificat reconnu."
    } catch {
        Write-Alerte "Certificat non installé ($($_.Exception.Message)). Dans le navigateur : « Paramètres avancés » puis « Continuer vers localhost »."
    }
}

function Show-Journal {
    Write-Host ''
    Write-Host "  Dernières lignes du journal des services :" -ForegroundColor DarkGray
    $null = Invoke-Compose @('logs', '--tail', '40', 'db', 'web')
    Write-Host ''
    Write-Host "  Relancez DEMARRER.cmd une fois la cause corrigée. Pour repartir de zéro : REINITIALISER-DEMO.cmd."
}

function Main {
    Write-Titre "FLUXAA Port — démarrage de la démonstration locale"
    Write-Host "  Dossier : $script:Racine"

    if (-not (Initialize-Docker)) { return }
    Write-Ok "Docker est prêt."

    Set-Location $script:Deploy
    if (-not (Test-InstallationLocale)) {
        Write-Echec "deploy\.env existe déjà et ne décrit pas une installation locale (DOMAIN=$(Read-EnvValue 'DOMAIN'))."
        Write-Host "  Ce lanceur ne gère que la démonstration locale (https://localhost/)."
        Write-Host "  Pour la démonstration : REINITIALISER-DEMO.cmd, puis DEMARRER.cmd. Pour une installation réelle : docs/DEPLOIEMENT.md."
        return
    }

    $premiere = -not (Test-Path $script:EnvFile)
    if ($premiere) {
        Write-Etape "Première installation : configuration et secrets (deploy\.env)…"
        $ports = Select-Ports
        if ($ports[0] -ne 443) {
            Write-Alerte "Les ports 443/80 sont occupés par un autre programme : la plateforme utilisera le port $($ports[0])."
        }
        New-EnvLocal $ports[0]
        Write-PortsOverride $ports[0] $ports[1]
        Write-Ok "Configuration écrite. Gardez une copie de deploy\.env (clés de cette installation)."
    }
    $url = Get-UrlLocale

    Write-Etape "Construction et démarrage des services…"
    if ($premiere) {
        Write-Host "  La première fois, l'image est construite (téléchargements) : comptez 5 à 15 minutes selon la connexion."
    }
    $code = Invoke-Compose @('up', '-d', '--build')
    if ($code -ne 0) {
        Write-Echec "Le démarrage des services a échoué (code $code)."
        Write-Host "  Causes fréquentes : connexion Internet coupée pendant la construction ; un autre programme occupe le port 443"
        Write-Host "  (le message contient alors « port is already allocated »)."
        Show-Journal
        return
    }

    Write-Etape "Initialisation de la base de données et de l'application…"
    if (-not (Wait-WebPret 900)) {
        Write-Echec "L'application ne répond pas."
        Show-Journal
        return
    }
    Write-Ok "Application prête."

    $etatDemo = Get-EtatDemo
    if ($etatDemo -eq 3) {
        Write-Etape "Chargement des données de démonstration (Lomé puis Freetown, une à deux minutes)…"
        $lignes = Load-Demo
        if ($null -eq $lignes) { Show-Journal; return }
        Write-Comptes $lignes
        Write-Ok "Données chargées. Comptes et clés : COMPTES-DEMO.txt (à la racine du dossier)."
    } elseif ($etatDemo -eq 0) {
        # Le tableau AIS montre les positions des 24 dernières heures : l'image de démonstration est réémise à chaque démarrage.
        Write-Etape "Image AIS de démonstration…"
        foreach ($port in @('TGLFW', 'SLFNA')) {
            $null = Invoke-ComposeCapture @('exec', '-T', 'web', 'python', 'manage.py', 'load_demo', '--port', $port, '--refresh-ais')
            if ($script:DernierCode -ne 0) { Write-Alerte "L'image AIS de démonstration de $port n'a pas pu être réémise (sans conséquence sur le reste)." }
        }
    } else {
        Write-Alerte "Impossible de vérifier les données de démonstration (code $etatDemo) ; elles ne sont pas rechargées."
    }

    Write-Etape "Certificat de l'adresse https://localhost…"
    Install-CertificatLocal

    Write-Etape "Ouverture du navigateur…"
    Start-Process $url
    Write-Host ''
    Write-Host "  La plateforme est prête : $url" -ForegroundColor Green
    Write-Host "  Mot de passe de tous les comptes de démonstration : $script:MotDePasseDemo"
    Write-Host "  Par exemple : age.tglfw@demo.fluxaa.test (agence, Lomé, en français) ou ter.slfna@demo.fluxaa.test (terminal, Freetown, en anglais)."
    Write-Host "  Les rôles qui décident (cap, apo, adm, sur) et dir demandent un code à 6 chiffres : CODES-DEMO.cmd le donne."
    Write-Host "  Tout est dans COMPTES-DEMO.txt ; démonstration en dix minutes : docs\GUIDE_UTILISATEUR.md."
    Write-Host "  Pour arrêter : ARRETER.cmd (les données sont conservées)."
    $script:Code = 0
}

try {
    Main
} catch {
    Write-Echec "Erreur inattendue : $($_.Exception.Message)"
    Write-Host "  $($_.ScriptStackTrace)" -ForegroundColor DarkGray
} finally {
    Pause-Fin
}
exit $script:Code
