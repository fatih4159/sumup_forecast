$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path '.venv/Scripts/python.exe')) {
    if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m venv .venv }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { & python -m venv .venv }
    else { throw 'Python 3 fehlt.' }
    if ($LASTEXITCODE -ne 0) { throw 'Virtuelle Umgebung konnte nicht erstellt werden.' }
}
$python = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
$stamp = '.venv/.requirements-installed'
if (-not (Test-Path $stamp) -or (Get-Item 'requirements.txt').LastWriteTimeUtc -gt (Get-Item $stamp).LastWriteTimeUtc) {
    & $python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Installation fehlgeschlagen.' }
    New-Item -ItemType File -Path $stamp -Force | Out-Null
}
& $python main.py @args
exit $LASTEXITCODE