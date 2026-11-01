# FLUXAA Port — arrêt de l'installation locale de démonstration (ARRETER.cmd).
# Les conteneurs sont arrêtés et retirés ; la base de données et les documents sont conservés dans
# les volumes Docker : DEMARRER.cmd retrouve tout. Windows PowerShell 5.1. Encodage : UTF-8 avec BOM.

. (Join-Path $PSScriptRoot 'commun.ps1')
$script:Code = 1

function Main {
    Write-Titre "FLUXAA Port — arrêt de la démonstration locale"
    $script:Docker = Find-Docker
    if (-not $script:Docker) {
        Write-Alerte "Docker Desktop n'est pas installé : rien à arrêter."
        $script:Code = 0
        return
    }
    if (-not (Test-DockerPret)) {
        Write-Alerte "Docker Desktop n'est pas démarré : la plateforme ne tourne pas."
        $script:Code = 0
        return
    }
    if (-not (Test-InstallationLocale)) {
        Write-Echec "deploy\.env ne décrit pas une installation locale : ce lanceur ne touche pas à une autre installation."
        return
    }
    Set-Location $script:Deploy
    Write-Etape "Arrêt des services…"
    $code = Invoke-Compose @('down')
    if ($code -ne 0) {
        Write-Echec "L'arrêt a échoué (code $code)."
        return
    }
    Write-Ok "Plateforme arrêtée. Les données sont conservées : DEMARRER.cmd la relance telle quelle."
    Write-Host "  Pour effacer aussi les données et repartir de zéro : REINITIALISER-DEMO.cmd."
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
