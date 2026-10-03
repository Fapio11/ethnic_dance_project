param(
    [string]$Python = "D:\miniconda\envs\dance3d_clean\python.exe",
    [int]$Port = 8765
)

$project = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $project
& $Python -m uvicorn server.app:app --host 127.0.0.1 --port $Port

