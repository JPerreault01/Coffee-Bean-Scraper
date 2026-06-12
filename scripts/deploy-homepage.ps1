# deploy-homepage.ps1
# One-command homepage deploy for Coffee Bean Index.
#
# What it does (no manual URL pasting anywhere):
#   1. scp the 3 homepage theme files to the VPS child theme.
#   2. scp the 5 converted WebPs (homepage-images/web/) to a temp dir on the VPS.
#   3. `wp media import` each WebP, delete any previously-imported homepage
#      attachments first (so re-deploys don't pile up duplicates), and store the
#      new attachment IDs in the `cbi_home_image_ids` option. The theme
#      (cbi_home_image_url / cbi_hero_head) reads that option, so the hero
#      background, hero preload, and the 4 card images all resolve automatically.
#   4. Flush the WP cache and report whether the hero CTA target page is published.
#
# Still manual afterwards (printed at the end): Cloudflare Purge Everything,
# a hard refresh, and a PageSpeed check.
#
# Prereqves: run convert-images.py first; SSH alias `cbi-prod` working
# (override with $env:CBI_SSH_HOST); passwordless `sudo -u www-data` on the VPS
# (set up in DEPLOY.md hardening).
#
# Usage (from repo root):  .\scripts\deploy-homepage.ps1

$ErrorActionPreference = 'Stop'

$RemoteHost = if ($env:CBI_SSH_HOST) { $env:CBI_SSH_HOST } else { 'cbi-prod' }
$ThemeDir   = '/var/www/coffeebeans/wp-content/themes/coffeebeanindex'
$RemoteTmp  = '/tmp/cbi-homepage'

$themeFiles = @(
    'wordpress-plugins/coffeebeanindex-theme/functions.php',
    'wordpress-plugins/coffeebeanindex-theme/front-page.php',
    'wordpress-plugins/coffeebeanindex-theme/style.css'
)

# --- Preflight ------------------------------------------------------------
foreach ($f in $themeFiles) {
    if (-not (Test-Path $f)) { Write-Host "Missing theme file: $f" -ForegroundColor Red; exit 1 }
}
$webps = Get-ChildItem 'homepage-images/web/*.webp' -ErrorAction SilentlyContinue
if (-not $webps -or $webps.Count -eq 0) {
    Write-Host "No WebPs in homepage-images/web/. Run: python convert-images.py" -ForegroundColor Red
    exit 1
}
Write-Host "Deploying to $RemoteHost : $($themeFiles.Count) theme files, $($webps.Count) images." -ForegroundColor Cyan

# --- 1. Theme files -------------------------------------------------------
foreach ($f in $themeFiles) {
    Write-Host "scp $f"
    scp $f "${RemoteHost}:$ThemeDir/"
    if ($LASTEXITCODE -ne 0) { Write-Host "scp failed: $f" -ForegroundColor Red; exit 1 }
}

# --- 2. Images to temp dir ------------------------------------------------
ssh $RemoteHost "mkdir -p $RemoteTmp"
if ($LASTEXITCODE -ne 0) { Write-Host "Could not create $RemoteTmp on $RemoteHost" -ForegroundColor Red; exit 1 }
foreach ($w in $webps) {
    Write-Host "scp $($w.Name)"
    scp $w.FullName "${RemoteHost}:$RemoteTmp/"
    if ($LASTEXITCODE -ne 0) { Write-Host "scp failed: $($w.Name)" -ForegroundColor Red; exit 1 }
}

# --- 3 + 4. Import media, set option, flush, report (remote) --------------
# Single-quoted here-string: PowerShell does NOT expand $vars; bash receives it verbatim.
$remote = @'
set -euo pipefail
WPPATH="/var/www/coffeebeans"
WP="sudo -u www-data wp --path=$WPPATH"
TMP="/tmp/cbi-homepage"

# option key -> source filename
PAIRS="hero:hero.webp espresso:espresso.webp dark_roast:dark_roast.webp beans:beans.webp ground_coffee:ground_coffee.webp"

# Remove previously-imported homepage attachments so re-deploys do not duplicate.
# `|| true` guards the first run, where the option does not exist yet and grep
# matches nothing (which would otherwise trip `set -o pipefail`).
OLD=$($WP option get cbi_home_image_ids --format=json 2>/dev/null || echo "{}")
{ echo "$OLD" | grep -oE ':[0-9]+' | tr -d ':' || true; } | while read -r id; do
  [ -n "$id" ] && $WP post delete "$id" --force >/dev/null 2>&1 || true
done

JSON="{"
SEP=""
for pair in $PAIRS; do
  key="${pair%%:*}"
  file="$TMP/${pair##*:}"
  if [ -f "$file" ]; then
    chmod a+r "$file" || true
    id=$($WP media import "$file" --porcelain)
    JSON="$JSON$SEP\"$key\":$id"
    SEP=","
    echo "imported $key -> attachment $id"
  else
    echo "WARN: missing $file (skipped)"
  fi
done
JSON="$JSON}"

$WP option update cbi_home_image_ids "$JSON" --format=json
echo "cbi_home_image_ids = $JSON"
$WP cache flush
echo "--- hero CTA target: /best-espresso-beans-under-20/ ---"
$WP post list --post_type=page --name=best-espresso-beans-under-20 --fields=ID,post_status,post_title --format=table || true
rm -rf "$TMP"
'@

Write-Host "Running media import + option update on $RemoteHost ..." -ForegroundColor Cyan
$remote | ssh $RemoteHost 'bash -s'
if ($LASTEXITCODE -ne 0) { Write-Host "Remote step failed (exit $LASTEXITCODE)." -ForegroundColor Red; exit 1 }

# --- Manual remainder -----------------------------------------------------
Write-Host ""
Write-Host "Homepage deployed. Manual steps left:" -ForegroundColor Green
Write-Host "  1. Cloudflare dashboard -> Caching -> Configuration -> Purge Everything"
Write-Host "  2. Hard-refresh the homepage (Ctrl+F5)"
Write-Host "  3. If the CTA page status above is not 'publish', publish /best-espresso-beans-under-20/"
Write-Host "  4. PageSpeed Insights on the homepage; confirm the hero is the LCP element"
