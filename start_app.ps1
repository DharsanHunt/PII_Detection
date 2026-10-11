# PowerShell One-Command Startup Script for Cadence PII Redaction Gateway
$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host " Cadence Financial Group — PII Detection & Redaction Gateway" -ForegroundColor Cyan
Write-Host " Starting FastAPI Backend (port 8000) & Vite Frontend (port 5173)" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

$BackendJob = Start-Process -FilePath "python" -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port 8000" -WorkingDirectory "$RootDir\backend" -PassThru -NoNewWindow
Write-Host "[+] FastAPI Backend started (PID: $($BackendJob.Id)) -> http://127.0.0.1:8000" -ForegroundColor Green

$FrontendJob = Start-Process -FilePath "npm.cmd" -ArgumentList "run dev -- --port 5173" -WorkingDirectory "$RootDir\frontend" -PassThru -NoNewWindow
Write-Host "[+] React + Vite Frontend started (PID: $($FrontendJob.Id)) -> http://localhost:5173" -ForegroundColor Green

Write-Host "`nPress Ctrl+C to stop servers." -ForegroundColor Yellow
Wait-Process -Id $BackendJob.Id, $FrontendJob.Id
