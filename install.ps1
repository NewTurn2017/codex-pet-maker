$ErrorActionPreference = "Stop"

# Install codex-pet-maker as a Codex skill bundle.
# Local checkout:  .\install.ps1
# Remote install:  irm https://raw.githubusercontent.com/NewTurn2017/codex-pet-maker/main/install.ps1 | iex

$RepoDefault = "NewTurn2017/codex-pet-maker"
$RefDefault = "main"

$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
$Target = if ($env:CODEX_PET_MAKER_TARGET) { $env:CODEX_PET_MAKER_TARGET } else { Join-Path $CodexHome "skills\codex-pet-maker" }
$Repo = if ($env:CODEX_PET_MAKER_REPO) { $env:CODEX_PET_MAKER_REPO } else { $RepoDefault }
$Ref = if ($env:CODEX_PET_MAKER_REF) { $env:CODEX_PET_MAKER_REF } else { $RefDefault }
$ArchiveUrl = if ($env:CODEX_PET_MAKER_ARCHIVE_URL) { $env:CODEX_PET_MAKER_ARCHIVE_URL } else { "https://github.com/$Repo/archive/refs/heads/$Ref.zip" }
$ArchivePath = if ($env:CODEX_PET_MAKER_ARCHIVE_PATH) { $env:CODEX_PET_MAKER_ARCHIVE_PATH } else { $null }
$PythonCommand = if ($env:PYTHON) { $env:PYTHON } else { "python" }

function Fail($Message) {
  Write-Error "codex-pet-maker install failed: $Message"
  exit 2
}

function Find-SourceRoot($Root) {
  if ((Test-Path (Join-Path $Root "SKILL.md")) -and (Test-Path (Join-Path $Root "pyproject.toml"))) {
    return (Resolve-Path $Root).Path
  }
  $Skill = Get-ChildItem -Path $Root -Filter "SKILL.md" -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($Skill) { return $Skill.DirectoryName }
  return $null
}

function Copy-SkillBundle($Source, $Destination) {
  $UnsafeTargets = @("", [System.IO.Path]::GetPathRoot($Destination), $HOME, $CodexHome)
  if ($UnsafeTargets -contains $Destination) { Fail "refusing unsafe install target: $Destination" }

  $Parent = Split-Path -Parent $Destination
  New-Item -ItemType Directory -Force -Path $Parent | Out-Null

  $SourceReal = (Resolve-Path $Source).Path
  $DestinationReal = if (Test-Path $Destination) { (Resolve-Path $Destination).Path } else { $null }
  if ($SourceReal -eq $DestinationReal) { return }

  $TempTarget = "$Destination.tmp.$PID"
  if (Test-Path $TempTarget) { Remove-Item -Recurse -Force $TempTarget }
  New-Item -ItemType Directory -Force -Path $TempTarget | Out-Null

  $Exclude = @(".git", ".venv", ".pytest_cache", ".omx", "__pycache__", "*.pyc", "*.egg-info", "pet-runs", "pet_request.json", "uv.lock")
  Get-ChildItem -Path $SourceReal -Force | Where-Object {
    $Name = $_.Name
    -not ($Exclude | Where-Object { $Name -like $_ })
  } | ForEach-Object {
    Copy-Item -Path $_.FullName -Destination $TempTarget -Recurse -Force
  }

  if (Test-Path $Destination) { Remove-Item -Recurse -Force $Destination }
  Move-Item -Path $TempTarget -Destination $Destination
}

function Get-RemoteSource() {
  $TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) "codex-pet-maker-$PID"
  if (Test-Path $TempRoot) { Remove-Item -Recurse -Force $TempRoot }
  New-Item -ItemType Directory -Force -Path $TempRoot | Out-Null

  $ZipPath = if ($ArchivePath) {
    if (-not (Test-Path $ArchivePath)) { Fail "archive not found: $ArchivePath" }
    (Resolve-Path $ArchivePath).Path
  } else {
    $Downloaded = Join-Path $TempRoot "source.zip"
    Invoke-WebRequest -Uri $ArchiveUrl -OutFile $Downloaded
    $Downloaded
  }

  $ExtractDir = Join-Path $TempRoot "extract"
  New-Item -ItemType Directory -Force -Path $ExtractDir | Out-Null
  Expand-Archive -Path $ZipPath -DestinationPath $ExtractDir -Force
  $Source = Find-SourceRoot $ExtractDir
  if (-not $Source) { Fail "downloaded archive does not contain SKILL.md" }
  return $Source
}

$LocalSource = $null
if ($MyInvocation.MyCommand.Path) {
  $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
  $LocalSource = Find-SourceRoot $ScriptDir
}

$Source = if ($LocalSource) { $LocalSource } else { Get-RemoteSource }
Copy-SkillBundle -Source $Source -Destination $Target

if ($env:CODEX_PET_MAKER_SKIP_VENV -ne "1") {
  $Python = Get-Command $PythonCommand -ErrorAction SilentlyContinue
  if (-not $Python) {
    $Python = Get-Command py -ErrorAction SilentlyContinue
    if ($Python) { $PythonCommand = "py" }
  }
  if (-not $Python) { Fail "Python executable not found. Install Python 3, or set `$env:PYTHON." }

  if ($PythonCommand -eq "py") {
    & py -3 -m venv (Join-Path $Target ".venv")
  } else {
    & $PythonCommand -m venv (Join-Path $Target ".venv")
  }
  $VenvPython = Join-Path $Target ".venv\Scripts\python.exe"
  & $VenvPython -m pip install --upgrade pip
  & $VenvPython -m pip install -e $Target
}

Write-Host "✅ codex-pet-maker installed"
Write-Host "Skill: $Target"
Write-Host "Python: $(Join-Path $Target '.venv\Scripts\python.exe')"
Write-Host ""
Write-Host "Restart Codex, then ask:"
Write-Host '  $codex-pet-maker make me a codex pet'
