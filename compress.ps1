param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$InputFile,

    [Parameter(Mandatory=$true, Position=1)]
    [int]$TargetSizeMB
)

if (-not (Test-Path $InputFile)) {
    Write-Error "Input file '$InputFile' not found."
    exit 1
}

$duration = & ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 $InputFile
if (-not $duration) {
    Write-Error "Unable to retrieve duration from '$InputFile'."
    exit 1
}

$sizeBits    = $TargetSizeMB * 1024 * 1024 * 8
$overhead    = 0.05
$usableBits  = $sizeBits * (1 - $overhead)
$bitrate_bps = [math]::Floor($usableBits / [double]$duration)
$bitrate_k   = [math]::Floor($bitrate_bps / 1024)

$baseName      = [System.IO.Path]::GetFileNameWithoutExtension($InputFile)
$outputFile    = "${baseName}_compressed.mp4"

ffmpeg -i $InputFile -c:v libx265 -b:v ${bitrate_k}k -an -y $outputFile

if ($LASTEXITCODE -eq 0) {
    Write-Host "Compression complete. Output saved as '$outputFile' (target: ${TargetSizeMB}MB)."
} else {
    Write-Error "ffmpeg failed with exit code $LASTEXITCODE."
    exit $LASTEXITCODE
}
