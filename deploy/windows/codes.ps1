# FLUXAA Port — codes à 6 chiffres (TOTP) des comptes de démonstration (CODES-DEMO.cmd).
# Lit les clés dans COMPTES-DEMO.txt et affiche le code courant de chaque compte, comme le ferait une
# application d'authentification. Réservé aux comptes de démonstration d'une installation locale.
# Windows PowerShell 5.1. Encodage du fichier : UTF-8 avec BOM.

. (Join-Path $PSScriptRoot 'commun.ps1')

function ConvertFrom-Base32([string]$texte) {
    $alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
    $texte = $texte.ToUpper().Replace(' ', '').TrimEnd('=')
    $bits = New-Object System.Text.StringBuilder
    foreach ($caractere in $texte.ToCharArray()) {
        $valeur = $alphabet.IndexOf($caractere)
        if ($valeur -lt 0) { throw "Clé TOTP invalide." }
        $null = $bits.Append([Convert]::ToString($valeur, 2).PadLeft(5, '0'))
    }
    $chaine = $bits.ToString()
    $octets = New-Object 'System.Collections.Generic.List[byte]'
    for ($i = 0; ($i + 8) -le $chaine.Length; $i += 8) {
        $octets.Add([Convert]::ToByte($chaine.Substring($i, 8), 2))
    }
    return ,$octets.ToArray()
}

function Get-CodeTotp([string]$cle, [long]$secondesUnix) {
    $octetsCle = ConvertFrom-Base32 $cle
    $compteur = [long][math]::Floor($secondesUnix / 30)
    $message = New-Object byte[] 8
    for ($i = 7; $i -ge 0; $i--) {
        $message[$i] = [byte]($compteur -band 0xFF)
        $compteur = $compteur -shr 8
    }
    $hmac = New-Object System.Security.Cryptography.HMACSHA1 -ArgumentList @(,$octetsCle)
    $empreinte = $hmac.ComputeHash($message)
    $decalage = $empreinte[19] -band 0x0F
    $nombre = (($empreinte[$decalage] -band 0x7F) -shl 24) -bor ($empreinte[$decalage + 1] -shl 16) -bor ($empreinte[$decalage + 2] -shl 8) -bor $empreinte[$decalage + 3]
    return ($nombre % 1000000).ToString('000000')
}

$script:Code = 1
try {
    Write-Titre "FLUXAA Port — codes à 6 chiffres des comptes de démonstration"
    if (-not (Test-Path $script:Comptes)) {
        Write-Echec "COMPTES-DEMO.txt introuvable : lancez d'abord DEMARRER.cmd."
    } else {
        $comptes = @()
        foreach ($ligne in Get-Content $script:Comptes -Encoding UTF8) {
            if ($ligne -match '^\s*([A-Z,]{3,})\s+(\S+@\S+)\s+([A-Z2-7]{16,})\s*$') {
                $comptes += New-Object PSObject -Property @{ Role = $Matches[1]; Compte = $Matches[2]; Cle = $Matches[3] }
            }
        }
        if ($comptes.Count -eq 0) {
            Write-Echec "Aucune clé TOTP dans COMPTES-DEMO.txt."
        } else {
            Write-Host "  Le code change toutes les 30 secondes : saisissez-le quand il lui reste au moins 5 secondes."
            Write-Host "  Appuyez sur une touche pour fermer."
            $precedent = -1
            while ($true) {
                $toucheDisponible = $false
                try { $toucheDisponible = [Console]::KeyAvailable } catch { }
                if ($toucheDisponible) { break }
                $unix = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
                $reste = 30 - ($unix % 30)
                if ($reste -ne $precedent) {
                    $precedent = $reste
                    Clear-Host
                    Write-Host ''
                    Write-Host ("  Codes valables encore {0,2} s   (une touche pour fermer)" -f $reste) -ForegroundColor Cyan
                    Write-Host ''
                    Write-Host ('  {0,-8}{1,-40}{2}' -f 'Rôle', 'Compte', 'Code') -ForegroundColor DarkGray
                    foreach ($compte in $comptes) {
                        $codeTotp = Get-CodeTotp $compte.Cle $unix
                        Write-Host ('  {0,-8}{1,-40}{2}' -f $compte.Role, $compte.Compte, $codeTotp)
                    }
                    Write-Host ''
                    Write-Host "  Mot de passe de tous les comptes : $script:MotDePasseDemo" -ForegroundColor DarkGray
                }
                Start-Sleep -Milliseconds 250
            }
            $script:Code = 0
        }
    }
} catch {
    Write-Echec "Erreur inattendue : $($_.Exception.Message)"
}
if ($script:Code -ne 0) { Pause-Fin }
exit $script:Code
