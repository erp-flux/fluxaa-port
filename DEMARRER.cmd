@echo off
rem FLUXAA Port - Demarre la plateforme sur cet ordinateur (demonstration locale) et ouvre le navigateur.
rem Double-cliquez sur ce fichier. Il lance deploy\windows\demarrer.ps1 avec Windows PowerShell.
rem Si Windows demande "Voulez-vous executer ce fichier ?" ou affiche "Windows a protege votre
rem ordinateur", choisissez "Informations complementaires" puis "Executer quand meme".
setlocal
title FLUXAA Port - demarrage
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\windows\demarrer.ps1"
if errorlevel 1 (
  echo.
  echo Le lanceur s'est termine avec une erreur. Lisez le message ci-dessus.
  pause
)
endlocal
