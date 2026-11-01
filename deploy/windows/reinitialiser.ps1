# FLUXAA Port — remise à zéro de l'installation locale de démonstration (REINITIALISER-DEMO.cmd).
# Arrête les services, EFFACE la base de données, les documents, la configuration (deploy\.env) et
# COMPTES-DEMO.txt. Le prochain DEMARRER.cmd repart d'une installation neuve. Demande confirmation.
# Windows PowerShell 5.1. Encodage : UTF-8 avec BOM.

. (Join-Path $PSScriptRoot 'commun.ps1')
$script:Code = 1

function Main {
    Write-Titre "FLUXAA Port — remise à zéro de la démonstration locale"
    $domaine = Read-EnvValue 'DOMAIN'
    if ($domaine) { Write-Host "  Installation décrite par deploy\.env : DOMAIN=$domaine" }
    Write-Host ''
    Write-Host "  Cette action efface définitivement, sur cet ordinateur :" -ForegroundColor Yellow
    Write-Host "   - la base de données de la plateforme (escales, journal, comptes) et la base de sûreté ;"
    Write-Host "   - les documents déposés ;"
    Write-Host "   - la configuration deploy\.env (clés et mots de passe de cette installation) et COMPTES-DEMO.txt."
    Write-Host "  Les sauvegardes éventuelles de deploy\backups ne sont pas touchées."
    Write-Host ''
    $reponse = Read-Host "Pour confirmer, tapez EFFACER puis Entrée (toute autre réponse annule)"
    if ($reponse -ne 'EFFACER') {
        Write-Ok "Rien n'a été modifié."
        $script:Code = 0
        return
    }

    $script:Docker = Find-Docker
    if ($script:Docker -and (Test-DockerPret) -and (Test-Path (Join-Path $script:Deploy 'docker-compose.yml'))) {
        Set-Location $script:Deploy
        Write-Etape "Arrêt des services et suppression des données…"
        $code = Invoke-Compose @('down', '--volumes', '--remove-orphans')
        if ($code -ne 0) {
            Write-Echec "La suppression a échoué (code $code) : les fichiers de configuration sont conservés."
            return
        }
    } else {
        Write-Alerte "Docker ne répond pas : seuls les fichiers de configuration sont effacés. Les volumes Docker"
        Write-Alerte "éventuels seront repris par la prochaine installation ou se suppriment depuis Docker Desktop."
    }
    foreach ($fichier in @($script:EnvFile, $script:PortsFile, $script:Comptes)) {
        if (Test-Path $fichier) { Remove-Item $fichier -Force }
    }
    Write-Ok "Installation effacée. DEMARRER.cmd recréera une installation neuve."
    $script:Code = 0
}

try {
    Main
} catch {
    Write-Echec "Erreur inattendue : $($_.Exception.Message)"
} finally {
    Pause-Fin
}
exit $script:Code
