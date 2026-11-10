@echo off
rem FLUXAA Port - Affiche les codes a 6 chiffres des comptes de demonstration qui decident.
rem Double-cliquez sur ce fichier. Il lance deploy\windows\codes.ps1 avec Windows PowerShell.
rem Si Windows demande "Voulez-vous executer ce fichier ?" ou affiche "Windows a protege votre
rem ordinateur", choisissez "Informations complementaires" puis "Executer quand meme".
setlocal
title FLUXAA Port - codes a 6 chiffres
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\windows\codes.ps1"
if errorlevel 1 (
  echo.
  echo Le lanceur s'est termine avec une erreur. Lisez le message ci-dessus.
  pause
)
endlocal
