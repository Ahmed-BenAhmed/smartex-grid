param(
    [switch]$IncludeRefit
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$RawDir = Join-Path $Root "data\raw"
New-Item -ItemType Directory -Force -Path $RawDir | Out-Null

function Download-IfMissing {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$OutFile
    )

    if (Test-Path $OutFile) {
        Write-Host "[data] exists: $OutFile"
        return
    }

    Write-Host "[data] downloading: $Url"
    Invoke-WebRequest -Uri $Url -OutFile $OutFile
}

$LondonUrl = "https://zenodo.org/records/4656091/files/london_smart_meters_dataset_without_missing_values.zip?download=1"
$LondonOut = Join-Path $RawDir "london_smart_meters_dataset_without_missing_values.zip"
Download-IfMissing -Url $LondonUrl -OutFile $LondonOut

$UciUrl = "https://archive.ics.uci.edu/static/public/235/individual+household+electric+power+consumption.zip"
$UciOut = Join-Path $RawDir "individual_household_electric_power_consumption.zip"
Download-IfMissing -Url $UciUrl -OutFile $UciOut

# UCI Morocco high-resolution smart-meter dataset (archive may be Excel/CSV)
$MoroccoUrl = "https://archive.ics.uci.edu/dataset/1158/high-resolution+load+dataset+from+smart+meters+across+various+cities+in+morocco"
$MoroccoOut = Join-Path $RawDir "morocco_high_resolution_smart_meters.zip"
Write-Host "[data] Note: the Morocco dataset page may require manual download or direct link retrieval."
Write-Host "       If the automatic download fails, visit: https://archive.ics.uci.edu/dataset/1158"
try {
    Download-IfMissing -Url $MoroccoUrl -OutFile $MoroccoOut
} catch {
    Write-Host "[data] Morocco dataset could not be downloaded automatically. Please download the archive from the UCI page and place it at: $MoroccoOut"
}

if ($IncludeRefit) {
    Write-Host "[data] REFIT requires using the Strathclyde dataset page if the direct file URL changes:"
    Write-Host "       https://pureportal.strath.ac.uk/en/datasets/refit-electrical-load-measurements/"
    Write-Host "       Download the cleaned archive into data\raw, then run scripts\prepare_datasets.py."
}

Write-Host "[data] downloads complete"
