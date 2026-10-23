<#
.SYNOPSIS
    Installs the HP Officejet K7100 / K7103 / K7108 printer driver on Windows 10/11
    without HP's legacy 2007 installer.

.DESCRIPTION
    The driver itself is HP's original Unidrv-based driver (version 61.063.264.22)
    taken from OJK7100_Full_8.exe and installed unmodified, so its Microsoft WHQL
    signature stays valid. Only the obsolete setup program is bypassed.

    Driver files are looked up in this order:
      1. -Source <folder>            a folder that contains hpoh710s.inf
      2. .\driver                    folder prepared by prepare.sh
      3. -Source <file.exe> or OJK7100_Full_8.exe next to this script or in .\vendor,
         extracted with tar.exe (Windows 10 1803+) or 7-Zip.

.PARAMETER Source
    Folder with the extracted driver or path to OJK7100_Full_8.exe.

.PARAMETER PrinterIP
    Optional. Creates a network queue (raw TCP 9100, HP JetDirect) for this address.
    USB printers need no parameter: Windows creates the queue when the printer is plugged in.

.EXAMPLE
    .\install.ps1
.EXAMPLE
    .\install.ps1 -Source D:\Downloads\OJK7100_Full_8.exe -PrinterIP 192.168.1.50
#>
[CmdletBinding()]
param(
    [string]$Source,
    [string]$PrinterIP,
    [string]$PrinterName = 'HP Officejet K7100',
    # Set when the script relaunches itself elevated: keeps the new window open at the end.
    [switch]$Elevated
)

$ErrorActionPreference = 'Stop'
$DriverName = 'HP Officejet K7100 Series'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal $id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
    Write-Host 'Requesting administrator rights...'
    $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$($MyInvocation.MyCommand.Path)`"", '-Elevated')
    foreach ($kv in $PSBoundParameters.GetEnumerator()) { $argList += "-$($kv.Key)", "`"$($kv.Value)`"" }
    Start-Process powershell.exe -Verb RunAs -ArgumentList $argList -Wait
    exit
}

$LogFile = Join-Path $env:TEMP 'hp_k7100_install.log'
Start-Transcript -Path $LogFile -Force | Out-Null
Write-Host "Windows $([Environment]::OSVersion.Version), log: $LogFile"

# Errors must stay readable: the elevated window would otherwise close immediately.
trap {
    Write-Host ''
    Write-Host "ERROR: $_" -ForegroundColor Red
    $setupLog = "$env:windir\INF\setupapi.dev.log"
    if (Test-Path $setupLog) {
        Write-Host '--- last driver-install entries from setupapi.dev.log ---'
        Get-Content $setupLog -Tail 60 | Write-Host
    }
    Stop-Transcript | Out-Null
    if ($Elevated) { Read-Host 'Press Enter to close' }
    exit 1
}

# --- Architecture -----------------------------------------------------------
# HP ships x64 and x86 binaries only (render plug-in, print processor, language
# monitor). ARM64 Windows cannot load them into its native spooler.
$arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
switch ($arch) {
    'X64'   { $inf = 'hpoh710s.inf' }
    'X86'   { $inf = 'hpoh710a.inf' }
    default { throw "Unsupported Windows architecture: $arch. HP's driver exists for x64 and x86 only." }
}

# --- Locate driver files ----------------------------------------------------
function Expand-HpPackage([string]$exe) {
    $dest = Join-Path $env:TEMP ('hp_k7100_' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $dest | Out-Null
    Write-Host "Extracting $exe ..."
    # OJK7100_Full_8.exe is a 7-Zip self-extracting archive; bsdtar in Windows reads 7z.
    & tar.exe -xf $exe -C $dest 2>$null
    if (-not (Test-Path (Join-Path $dest $inf))) {
        $sevenZip = @("$env:ProgramFiles\7-Zip\7z.exe", "${env:ProgramFiles(x86)}\7-Zip\7z.exe") |
                    Where-Object { Test-Path $_ } | Select-Object -First 1
        if (-not $sevenZip) {
            throw "Could not extract $exe. Install 7-Zip (https://www.7-zip.org) or run prepare.sh on macOS/Linux."
        }
        & $sevenZip x -y "-o$dest" $exe | Out-Null
    }
    if (-not (Test-Path (Join-Path $dest $inf))) { throw "$inf not found inside $exe" }
    return $dest
}

$driverDir = $null
if ($Source -and (Test-Path $Source -PathType Container)) {
    $driverDir = $Source
} elseif (Test-Path (Join-Path $Here "driver\$inf")) {
    $driverDir = Join-Path $Here 'driver'
} else {
    $exe = $Source
    if (-not $exe) {
        $exe = @((Join-Path $Here 'OJK7100_Full_8.exe'), (Join-Path $Here 'vendor\OJK7100_Full_8.exe')) |
               Where-Object { Test-Path $_ } | Select-Object -First 1
    }
    if (-not $exe -or -not (Test-Path $exe)) {
        throw 'Driver not found. Put OJK7100_Full_8.exe next to this script or pass -Source.'
    }
    $driverDir = Expand-HpPackage (Resolve-Path $exe).Path
}
$infPath = Join-Path $driverDir $inf
if (-not (Test-Path $infPath)) { throw "$infPath not found" }

# --- Signature --------------------------------------------------------------
$cat = [IO.Path]::ChangeExtension($infPath, '.cat')
$sig = Get-AuthenticodeSignature $cat
Write-Host "Catalog signature: $($sig.Status) ($($sig.SignerCertificate.Subject))"
if ($sig.Status -ne 'Valid') {
    Write-Warning 'The catalog signature is not valid; Windows will probably refuse the driver.'
}

# --- Install ----------------------------------------------------------------
Write-Host "Adding $inf to the driver store..."
& pnputil.exe /add-driver $infPath /install
# 0 = ok, 259 = added but no matching device connected, 3010 = reboot required
if ($LASTEXITCODE -notin 0, 259, 3010) { throw "pnputil failed with exit code $LASTEXITCODE" }

if (-not (Get-PrinterDriver -Name $DriverName -ErrorAction SilentlyContinue)) {
    Write-Host "Registering printer driver '$DriverName'..."
    try {
        Add-PrinterDriver -Name $DriverName
    } catch {
        # Fallback for systems where the PrintManagement cmdlet cannot see the store entry.
        & rundll32.exe printui.dll,PrintUIEntry /ia /m "$DriverName" /f "$infPath"
    }
}

if ($PrinterIP) {
    $port = "IP_$PrinterIP"
    if (-not (Get-PrinterPort -Name $port -ErrorAction SilentlyContinue)) {
        Add-PrinterPort -Name $port -PrinterHostAddress $PrinterIP -PortNumber 9100
    }
    if (-not (Get-Printer -Name $PrinterName -ErrorAction SilentlyContinue)) {
        Add-Printer -Name $PrinterName -DriverName $DriverName -PortName $port
    }
    Write-Host "Network printer '$PrinterName' created on ${PrinterIP}:9100."
} else {
    # Let PnP pick up a K7100 that is already plugged in over USB.
    & pnputil.exe /scan-devices 2>$null | Out-Null
}

Write-Host ''
Write-Host "Done. Driver '$DriverName' is installed."
Write-Host 'USB: connect (or reconnect) the printer and Windows will create the queue automatically.'
Stop-Transcript | Out-Null
if ($Elevated) { Read-Host 'Press Enter to close' }
