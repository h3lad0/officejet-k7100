<#
.SYNOPSIS
    Removes the HP Officejet K7100 driver installed by install.ps1
    (printer queues that use it, the spooler driver and the driver-store package).
#>
$ErrorActionPreference = 'Stop'
$DriverName = 'HP Officejet K7100 Series'

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not (New-Object Security.Principal.WindowsPrincipal $id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process powershell.exe -Verb RunAs -Wait -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$($MyInvocation.MyCommand.Path)`"")
    exit
}

Get-Printer | Where-Object DriverName -eq $DriverName | ForEach-Object {
    Write-Host "Removing printer '$($_.Name)'"
    Remove-Printer -Name $_.Name
}

if (Get-PrinterDriver -Name $DriverName -ErrorAction SilentlyContinue) {
    Write-Host "Removing printer driver '$DriverName'"
    Remove-PrinterDriver -Name $DriverName -RemoveFromDriverStore -ErrorAction SilentlyContinue
}

# Driver-store packages that may remain (published as oemNN.inf).
Get-WindowsDriver -Online | Where-Object { $_.OriginalFileName -match 'hpoh710[as]\.inf$' } | ForEach-Object {
    Write-Host "Deleting driver package $($_.Driver)"
    & pnputil.exe /delete-driver $_.Driver /uninstall /force
}

Write-Host 'Done.'
