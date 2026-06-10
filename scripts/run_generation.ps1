# Auto-generated generation runner — safe to delete after use
param([string]$ApiKey)

if ($ApiKey) { $env:CLAUDE_API_KEY = $ApiKey }

$date = Get-Date -Format "yyyy-MM-dd"
$logFile = "drafts\generation-log-$date.txt"
$failedIds = @()
$failedOutput = @{}
$skipped = 0
$generated = 0

$ids = py -c "import json; [print(b['id']) for b in json.load(open('scrapers/products.json'))]"

foreach ($id in $ids) {
    $out = "drafts\$id-$date.md"
    if (Test-Path $out) {
        "SKIP $id (draft exists)" | Tee-Object -FilePath $logFile -Append
        $skipped++
        continue
    }
    "=== generating $id ===" | Tee-Object -FilePath $logFile -Append
    $errFile = "drafts\.err-$id.tmp"
    $proc = Start-Process -FilePath "py" `
        -ArgumentList "scrapers\generate_review.py", $id `
        -NoNewWindow -Wait -PassThru `
        -RedirectStandardError $errFile
    if ($proc.ExitCode -ne 0) {
        "FAILED $id (exit $($proc.ExitCode))" | Tee-Object -FilePath $logFile -Append
        if (Test-Path $errFile) {
            $errContent = Get-Content $errFile -Tail 10
            $failedOutput[$id] = $errContent -join "`n"
            $errContent | ForEach-Object { "  ERR: $_" } | Tee-Object -FilePath $logFile -Append
        }
        $failedIds += $id
    } else {
        $generated++
        "OK $id" | Tee-Object -FilePath $logFile -Append
    }
    if (Test-Path $errFile) { Remove-Item $errFile -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
}

"" | Tee-Object -FilePath $logFile -Append
"=== Generation complete ===" | Tee-Object -FilePath $logFile -Append
"Generated: $generated" | Tee-Object -FilePath $logFile -Append
"Skipped:   $skipped" | Tee-Object -FilePath $logFile -Append
"Failed:    $($failedIds.Count)" | Tee-Object -FilePath $logFile -Append
if ($failedIds.Count -gt 0) {
    "Failed IDs: $($failedIds -join ', ')" | Tee-Object -FilePath $logFile -Append
    foreach ($fid in $failedIds) {
        "--- $fid error output ---" | Tee-Object -FilePath $logFile -Append
        if ($failedOutput[$fid]) { $failedOutput[$fid] | Tee-Object -FilePath $logFile -Append }
    }
}
$draftCount = (Get-ChildItem "drafts\*.md" -Exclude "generation-log*" -ErrorAction SilentlyContinue).Count
"Draft .md files in .\drafts\: $draftCount" | Tee-Object -FilePath $logFile -Append
