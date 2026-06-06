# sync_drafts.ps1
# Copies all local draft .md files to the VPS /opt/drafts/ directory.
# Run from the repo root after generating reviews locally.
# Usage: .\scripts\sync_drafts.ps1
# Requires: SSH key auth configured for root@142.93.127.178

$VPS = "root@142.93.127.178"
$LOCAL_DRAFTS = ".\drafts"
$REMOTE_DRAFTS = "/opt/drafts/"

$files = Get-ChildItem -Path $LOCAL_DRAFTS -Filter "*.md" -ErrorAction SilentlyContinue
if (-not $files) {
    Write-Host "No draft files found in .\drafts — generate reviews first."
    exit 1
}

Write-Host "Syncing $($files.Count) draft(s) to VPS..."
scp "$LOCAL_DRAFTS\*.md" "${VPS}:${REMOTE_DRAFTS}"

if ($LASTEXITCODE -eq 0) {
    Write-Host "Done. $($files.Count) draft(s) uploaded to ${VPS}:${REMOTE_DRAFTS}"
} else {
    Write-Host "scp failed with exit code $LASTEXITCODE — check SSH connectivity."
    exit 1
}
