@echo off
rem FLUXAA Port - Efface l'installation locale de demonstration (confirmation demandee).
rem Double-cliquez sur ce fichier. Il lance deploy\windows\reinitialiser.ps1 avec Windows PowerShell.
rem Si Windows demande "Voulez-vous executer ce fichier ?" ou affiche "Windows a protege votre
rem ordinateur", choisissez "Informations complementaires" puis "Executer quand meme".
setlocal
title FLUXAA Port - remise a zero
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\windows\reinitialiser.ps1"
if errorlevel 1 (
  echo.
  echo Le lanceur s'est termine avec une erreur. Lisez le message ci-dessus.
  pause
)
endlocal
