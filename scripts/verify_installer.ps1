<#
Runs a real install/reinstall/uninstall with a temporary program directory and
isolated application data. Refuses to touch an existing installed PrepaPilot.
The portable working application is never used. Run with PowerShell 7 and Python
3 (standard library only); pass -Python to select its executable if needed.
With -PreviousInstaller, verifies an upgrade from that older Setup instead of
reinstalling the same release. Both language self-tests run after replacement.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Installer,
    [string]$PreviousInstaller,
    [string]$Python = 'python'
)

$ErrorActionPreference = 'Stop'
$repoPrepa = Split-Path -Parent $PSScriptRoot
$installerPrepa = (Resolve-Path -LiteralPath $Installer).Path
$previousInstallerPrepa = $null
if ($PreviousInstaller) { $previousInstallerPrepa = (Resolve-Path -LiteralPath $PreviousInstaller).Path }

function Get-PrepaInstallerVersion([string]$setupPathPrepa) {
    if (-not (Test-Path -LiteralPath $setupPathPrepa -PathType Leaf) -or
        [IO.Path]::GetFileName($setupPathPrepa) -cnotmatch '^PrepaPilot-([0-9]+\.[0-9]+\.[0-9]+)-Setup\.exe$') {
        throw 'Le nom de chaque installateur doit respecter PrepaPilot-X.Y.Z-Setup.exe.'
    }
    return $Matches[1]
}

$expectedVersionPrepa = Get-PrepaInstallerVersion $installerPrepa
$previousVersionPrepa = $null
if ($null -ne $previousInstallerPrepa) {
    $previousVersionPrepa = Get-PrepaInstallerVersion $previousInstallerPrepa
    if ([version]$previousVersionPrepa -ge [version]$expectedVersionPrepa) {
        throw 'PreviousInstaller doit désigner une version plus ancienne que Installer.'
    }
}
& $Python -c 'import sqlite3' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Python 3 avec sqlite3 est nécessaire pour vérifier les préférences enregistrées. Fournis son chemin avec -Python.' }
$uninstallKeysPrepa = @(
    'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{01202F3A-A35E-4ED8-8D43-14612EE01D8F}_is1',
    'HKCU:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\{01202F3A-A35E-4ED8-8D43-14612EE01D8F}_is1'
)
foreach ($keyPrepa in $uninstallKeysPrepa) {
    if (Test-Path -LiteralPath $keyPrepa) { throw 'Une installation de PrépaPilot existe déjà sur ce compte. Utilise un compte Windows de test.' }
}
$testBasePrepa = Join-Path $repoPrepa '.build/installer-tests'
New-Item -ItemType Directory -Path $testBasePrepa -Force | Out-Null
$testRootPrepa = Join-Path (Resolve-Path -LiteralPath $testBasePrepa).Path ([guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRootPrepa | Out-Null
$appDirPrepa = Join-Path $testRootPrepa 'Application'
$userDirPrepa = Join-Path $testRootPrepa 'Utilisateur'
$uninstallerPrepa = Join-Path $appDirPrepa 'unins000.exe'
$oldLocalPrepa = $env:LOCALAPPDATA
$oldQtPrepa = $env:QT_QPA_PLATFORM
$ownedProcessPrepa = $null
$installedPrepa = $false

function Invoke-PrepaSetup([string]$setupPathPrepa, [string]$logNamePrepa) {
    $logPrepa = Join-Path $testRootPrepa $logNamePrepa
    $argsPrepa = @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/NOICONS','/TASKS=""',
        ('/DIR="' + $appDirPrepa + '"'), ('/LOG="' + $logPrepa + '"'))
    $setupPrepa = Start-Process -FilePath $setupPathPrepa -ArgumentList $argsPrepa -WindowStyle Hidden -PassThru
    if (-not $setupPrepa.WaitForExit(120000)) { throw "Le test d’installation a dépassé deux minutes." }
    if ($setupPrepa.ExitCode -ne 0) { throw ("Échec de l’installation, code " + $setupPrepa.ExitCode + '. Voir ' + $logPrepa) }
}

function Assert-PrepaVersion([string]$expectedPrepa) {
    $actualPrepa = [Diagnostics.FileVersionInfo]::GetVersionInfo($exePrepa).FileVersion
    if ($actualPrepa -ne $expectedPrepa) {
        throw ("Version installée incorrecte : attendue " + $expectedPrepa + ', obtenue ' + $actualPrepa + '.')
    }
}

function Assert-PrepaDataUnchanged([string]$operationPrepa) {
    if ((Get-FileHash -LiteralPath $databasePrepa -Algorithm SHA256).Hash -ne $databaseHashPrepa -or
        (Get-FileHash -LiteralPath $sentinelPrepa -Algorithm SHA256).Hash -ne $sentinelHashPrepa) {
        throw ($operationPrepa + ' a modifié les données.')
    }
}

function Assert-PrepaEnglishPreference {
    # Read the real installed database without changing it or importing the app.
    $checkPrepa = @'
import json
from pathlib import Path
import sqlite3
import sys

with sqlite3.connect(Path(sys.argv[1]).resolve().as_uri() + '?mode=ro', uri=True) as connection:
    row = connection.execute("SELECT value FROM settings WHERE key='desktop_language'").fetchone()
    if row is None or json.loads(row[0]) != 'en':
        raise SystemExit('The installed application did not persist its English preference.')
'@
    & $Python -c $checkPrepa $databasePrepa
    if ($LASTEXITCODE -ne 0) { throw "La langue anglaise n’a pas été conservée dans les données de la version installée." }
}

try {
    $initialInstallerPrepa = if ($null -ne $previousInstallerPrepa) { $previousInstallerPrepa } else { $installerPrepa }
    Invoke-PrepaSetup $initialInstallerPrepa 'installation.log'
    $installedPrepa = $true
    $exePrepa = Join-Path $appDirPrepa 'PrepaPilot.exe'
    if (-not (Test-Path -LiteralPath $exePrepa)) { throw 'Exécutable installé absent.' }
    $initialVersionPrepa = if ($null -ne $previousVersionPrepa) { $previousVersionPrepa } else { $expectedVersionPrepa }
    Assert-PrepaVersion $initialVersionPrepa
    $markerPrepa = Get-Content -LiteralPath (Join-Path $appDirPrepa 'installation.json') -Raw | ConvertFrom-Json
    if ($markerPrepa.data_mode -ne 'localappdata') { throw 'Marqueur de stockage installé incorrect.' }
    if (Test-Path -LiteralPath (Join-Path $appDirPrepa 'data')) { throw "L’installation contient déjà des données." }

    # The normal launch, unlike --self-test, exercises the compiled data path.
    $env:LOCALAPPDATA = $userDirPrepa
    $env:QT_QPA_PLATFORM = 'offscreen'
    $ownedProcessPrepa = Start-Process -FilePath $exePrepa -ArgumentList @('--language','en') -WorkingDirectory $appDirPrepa -WindowStyle Hidden -PassThru
    $databasePrepa = Join-Path $userDirPrepa 'PrepaPilot/data/mpsi.sqlite3'
    $deadlinePrepa = [DateTime]::UtcNow.AddSeconds(45)
    while (-not (Test-Path -LiteralPath $databasePrepa)) {
        if ($ownedProcessPrepa.HasExited) { throw 'Le lancement installé normal a échoué.' }
        if ([DateTime]::UtcNow -gt $deadlinePrepa) { throw "La base installée n’a pas été créée dans le dossier utilisateur isolé." }
        Start-Sleep -Milliseconds 200
    }
    Start-Sleep -Seconds 2
    if (Test-Path -LiteralPath (Join-Path $appDirPrepa 'data')) { throw 'Le mode installé a utilisé un dossier data près du programme.' }
    if (-not $ownedProcessPrepa.HasExited) { Stop-Process -Id $ownedProcessPrepa.Id -Force; $ownedProcessPrepa.WaitForExit() }
    $ownedProcessPrepa = $null
    Assert-PrepaEnglishPreference

    $sentinelPrepa = Join-Path $userDirPrepa 'PrepaPilot/data/verification-conservation.txt'
    Set-Content -LiteralPath $sentinelPrepa -Value 'Données fictives à conserver après mise à jour, réinstallation et désinstallation.' -Encoding utf8
    $databaseHashPrepa = (Get-FileHash -LiteralPath $databasePrepa -Algorithm SHA256).Hash
    $sentinelHashPrepa = (Get-FileHash -LiteralPath $sentinelPrepa -Algorithm SHA256).Hash

    $replacementLogPrepa = if ($null -ne $previousInstallerPrepa) { 'mise-a-jour.log' } else { 'reinstallation.log' }
    # The existing installation stays registered: no uninstall occurs between Setups.
    Invoke-PrepaSetup $installerPrepa $replacementLogPrepa
    Assert-PrepaVersion $expectedVersionPrepa
    Assert-PrepaDataUnchanged 'Le remplacement du programme'
    Assert-PrepaEnglishPreference

    # Always exercise the new executable, with no success marker left by an old run.
    foreach ($languagePrepa in @('fr', 'en')) {
        $selfTestMarkerPrepa = Join-Path $appDirPrepa 'self-test-ok.txt'
        $selfTestLogPrepa = Join-Path $appDirPrepa 'self-test.log'
        foreach ($diagnosticPrepa in @($selfTestMarkerPrepa, $selfTestLogPrepa)) {
            if (Test-Path -LiteralPath $diagnosticPrepa) { Remove-Item -LiteralPath $diagnosticPrepa }
        }
        $ownedProcessPrepa = Start-Process -FilePath $exePrepa -ArgumentList @('--self-test','--language',$languagePrepa) -WorkingDirectory $appDirPrepa -WindowStyle Hidden -PassThru
        if (-not $ownedProcessPrepa.WaitForExit(120000)) { throw ("L’autotest installé en " + $languagePrepa + " a dépassé deux minutes.") }
        if ($ownedProcessPrepa.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $selfTestMarkerPrepa)) { throw ("L’autotest de la version installée en " + $languagePrepa + " a échoué.") }
        $ownedProcessPrepa = $null
    }
    Assert-PrepaEnglishPreference
    Assert-PrepaDataUnchanged 'Les autotests de la nouvelle version'

    $uninstallPrepa = Start-Process -FilePath $uninstallerPrepa -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',('/LOG="' + (Join-Path $testRootPrepa 'desinstallation.log') + '"')) -WindowStyle Hidden -PassThru
    if (-not $uninstallPrepa.WaitForExit(120000) -or $uninstallPrepa.ExitCode -ne 0) { throw 'La désinstallation a échoué.' }
    $installedPrepa = $false
    if (Test-Path -LiteralPath $exePrepa) { throw "La désinstallation a conservé l’exécutable." }
    Assert-PrepaDataUnchanged 'La désinstallation'
    foreach ($keyPrepa in $uninstallKeysPrepa) {
        if (Test-Path -LiteralPath $keyPrepa) { throw 'La désinstallation a conservé son inscription Windows.' }
    }
    [ordered]@{
        installer = [IO.Path]::GetFileName($installerPrepa)
        sha256 = (Get-FileHash -LiteralPath $installerPrepa -Algorithm SHA256).Hash.ToLowerInvariant()
        previous_installer = if ($null -ne $previousInstallerPrepa) { [IO.Path]::GetFileName($previousInstallerPrepa) } else { $null }
        initial_version = $initialVersionPrepa
        installed_version_verified = $expectedVersionPrepa
        installation = 'OK'
        normal_launch_user_data = 'OK'
        english_preference_persisted = 'OK'
        installed_self_test_french = 'OK'
        installed_self_test_english = 'OK'
        reinstall_preserves_data = if ($null -eq $previousInstallerPrepa) { 'OK' } else { 'not requested' }
        upgrade_preserves_data = if ($null -ne $previousInstallerPrepa) { 'OK' } else { 'not requested' }
        uninstall_preserves_data = 'OK'
        windows_registration_removed = 'OK'
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $testRootPrepa 'resultat.json') -Encoding utf8
    $replacementPrepa = if ($null -ne $previousInstallerPrepa) { 'mise à jour' } else { 'réinstallation' }
    Write-Output ('Installation, lancement, ' + $replacementPrepa + ', autotests bilingues et désinstallation vérifiés : ' + $testRootPrepa)
}
finally {
    if ($null -ne $ownedProcessPrepa -and -not $ownedProcessPrepa.HasExited) { Stop-Process -Id $ownedProcessPrepa.Id -Force }
    $env:LOCALAPPDATA = $oldLocalPrepa
    $env:QT_QPA_PLATFORM = $oldQtPrepa
    if ($installedPrepa -and (Test-Path -LiteralPath $uninstallerPrepa)) {
        Start-Process -FilePath $uninstallerPrepa -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART') -WindowStyle Hidden -Wait | Out-Null
    }
}
