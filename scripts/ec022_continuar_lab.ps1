#requires -Version 7.0
<# Continue only the existing EC-022 stack. No init, start, reset, stop, destroy,
   link, remote commands, or changes to another stack. #>
param([Parameter(Mandatory=$true)][string]$RepoPath, [switch]$Publicar)
$ErrorActionPreference = 'Stop'
$repo=(Resolve-Path -LiteralPath $RepoPath).Path
$id='ec022lab08f2e7bbd3db'
$lab=Join-Path (Split-Path $repo -Parent) $id
$config=Join-Path $lab 'supabase/config.jsonc'
$prototype=Join-Path $repo 'docs/ec022/prototipo_almacenamiento.sql'
$sqlTests=Join-Path $repo 'tests/ec022_almacenamiento_aislado.sql'
$migration=Join-Path $lab 'supabase/migrations/20261127232951_ec022_lab_candidate.sql'
foreach ($path in @($config,$prototype,$sqlTests,$migration)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing expected file: $path" }
}
if ((Get-Content -LiteralPath $config -Raw) -notmatch '"project_id"\s*:\s*"ec022lab08f2e7bbd3db"') {
    throw 'The laboratory project identity does not match.'
}
if (Test-Path -LiteralPath (Join-Path $lab 'supabase/.temp/project-ref')) {
    throw 'Unexpected linked project marker: refusing to continue.'
}
foreach ($cmd in @('docker','npx.cmd','python','git')) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw "Missing executable: $cmd" }
}
$psql=(Get-Command psql.exe -ErrorAction SilentlyContinue).Source
if (-not $psql -and (Test-Path 'C:/Program Files/PostgreSQL/17/bin/psql.exe')) { $psql='C:/Program Files/PostgreSQL/17/bin/psql.exe' }
if (-not $psql) { throw 'psql.exe is required.' }
$oldExperimental=$env:SUPABASE_EXPERIMENTAL_STACK
$oldPassword=$env:PGPASSWORD
$oldDsn=$env:EC022_TEST_DSN
$oldDisposable=$env:EC022_DISPOSABLE_TEST_CLUSTER
try {
    $env:SUPABASE_EXPERIMENTAL_STACK='1'
    Write-Host "Inspecting existing local stack $id"
    & docker version --format '{{.Server.Version}}'
    if ($LASTEXITCODE -ne 0) { throw 'Docker is unavailable.' }
    # Capture only JSON because it includes local keys; stderr remains visible.
    $statusText=(& npx.cmd --yes supabase@3.4.0 stack status --workdir $lab --stack $id --output-format json | Out-String)
    if ($LASTEXITCODE -ne 0) { throw 'The named existing local stack is unavailable.' }
    $status=$statusText | ConvertFrom-Json
    $dbUrl=[string]$status.env.DB_URL
    if (-not $dbUrl) { throw 'The named stack has no database URL.' }
    try { $uri=[uri]$dbUrl } catch { throw 'Invalid local database URL.' }
    if ($uri.Host -notin @('127.0.0.1','localhost','::1') -or $uri.Port -le 0 -or $uri.AbsolutePath.TrimStart('/') -ne 'postgres') {
        throw 'Refusing a non-loopback or unexpected database.'
    }
    $userinfo=$uri.UserInfo.Split(':',2)
    if ($userinfo.Count -ne 2 -or [uri]::UnescapeDataString($userinfo[0]) -ne 'postgres') { throw 'Unexpected database identity.' }
    $env:PGPASSWORD=[uri]::UnescapeDataString($userinfo[1])
    $base=@('-X','-h',$uri.Host,'-p',"$($uri.Port)",'-U','postgres','-d','postgres','-v','ON_ERROR_STOP=1')
    $inspection="select json_build_object('roles',(select count(*) from pg_roles where rolname in ('ec022_ingestor','ec022_validador','ec022_lector_aprobaciones','ec022_escritor_funcion')),'schema',to_regnamespace('ec022_privado') is not null,'series',to_regclass('public.ec022_series') is not null,'observaciones',to_regclass('public.ec022_observaciones') is not null,'aprobaciones',to_regclass('public.ec022_aprobaciones') is not null,'history',(select count(*) from supabase_migrations.schema_migrations where version='20261127232951'))::text;"
    $inspectionJson=(& $psql @base -t -A -c $inspection | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Database preflight query failed.' }
    $state=$inspectionJson | ConvertFrom-Json
    Write-Host ("Preflight: roles={0}, private_schema={1}, series={2}, observations={3}, approvals={4}, migration_history={5}" -f $state.roles,$state.schema,$state.series,$state.observaciones,$state.aprobaciones,$state.history)
    $oldHash='d2ad581f92e0886202035d3149a918a21ef6d084'
    $currentHash=(& git -C $repo hash-object $migration).Trim()
    $correctedHash=(& git -C $repo hash-object $prototype).Trim()
    if ($currentHash -notin @($oldHash,$correctedHash)) { throw 'The existing migration file was modified unexpectedly; no file was overwritten.' }
    if ($state.history -eq 0) {
        if ($state.roles -ne 0 -or $state.schema -or $state.series -or $state.observaciones -or $state.aprobaciones) {
            throw 'Partial EC-022 objects exist without migration history. No objects were removed; inspect this state before retrying.'
        }
        if ($currentHash -eq $oldHash) {
            $backup="$migration.before-role-fix.bak"
            if (Test-Path -LiteralPath $backup) { throw 'Migration backup already exists; refusing to overwrite it.' }
            Copy-Item -LiteralPath $migration -Destination $backup
            Copy-Item -LiteralPath $prototype -Destination $migration
        }
        Write-Host 'Applying corrected candidate to this named local stack.'
        & npx.cmd --yes supabase@3.4.0 migration up --workdir $lab --stack $id
        if ($LASTEXITCODE -ne 0) { throw 'Local migration failed; see the SQL error above.' }
    } elseif ($state.history -eq 1 -and $currentHash -eq $correctedHash -and $state.roles -eq 4 -and $state.schema -and $state.series -and $state.observaciones -and $state.aprobaciones) {
        Write-Host 'Corrected candidate already applied; checking the test fixture before continuing.'
    } else { throw 'Migration history and database objects are inconsistent; no repair was attempted.' }

    $existing=(& $psql @base -t -A -c "select count(*) from public.ec022_series where serie='test';" | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect the test fixture.' }
    if ($existing -ne '0') { throw 'A test fixture already exists. No test rows were deleted or overwritten; inspect prior run state.' }
    & $psql @base -f $sqlTests
    if ($LASTEXITCODE -ne 0) { throw 'SQL integration test failed; see the database error above.' }
    & $psql @base -c "set role ec022_validador; insert into public.ec022_aprobaciones (serie,periodo,fuente_sha256,accion,motivo) values ('test','2020-01-01',repeat('b',64),'aprobar','API test');"
    if ($LASTEXITCODE -ne 0) { throw 'Could not prepare the local REST fixture.' }
    $apiUrl=[string]$status.env.API_URL
    $anonKey=[string]$status.env.ANON_KEY
    try { $apiUri=[uri]$apiUrl } catch { throw 'Invalid local API URL.' }
    if (-not $anonKey -or $apiUri.Host -notin @('127.0.0.1','localhost','::1') -or $apiUri.Scheme -ne 'http') { throw 'Unexpected local REST endpoint.' }
    $headers=@{apikey=$anonKey; Authorization="Bearer $anonKey"}
    try { $rows=@((Invoke-RestMethod -Uri "$apiUrl/rest/v1/ec022_observaciones?select=serie,valor&serie=eq.test" -Headers $headers -MaximumRedirection 0) | ForEach-Object { $_ }) }
    catch { throw "Local REST read failed: $($_.Exception.Message)" }
    if ($rows.Count -ne 1 -or [decimal]$rows[0].valor -ne 101) { throw 'REST did not return exactly the approved edition.' }
    $denied=$false
    try { Invoke-RestMethod -Uri "$apiUrl/rest/v1/ec022_aprobaciones?select=evento" -Headers $headers -MaximumRedirection 0 | Out-Null }
    catch { if ([int]$_.Exception.Response.StatusCode -in @(401,403,404)) { $denied=$true } else { throw "Approval access test failed: $($_.Exception.Message)" } }
    if (-not $denied) { throw 'Anonymous REST access to approvals was not denied.' }
    Write-Host 'REST: approved observation visible; approvals denied.'

    $venv=Join-Path $lab '.venv'
    $py=Join-Path $venv 'Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $py)) {
        if (Test-Path -LiteralPath $venv) { throw 'An incomplete .venv exists; it was not modified.' }
        & python -m venv $venv
        if ($LASTEXITCODE -ne 0) { throw 'Creating the lab Python environment failed.' }
    }
    & $py -m pip install -r (Join-Path $repo 'requirements-ec022.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Installing pinned dependencies failed.' }
    Push-Location $repo
    try {
        & $py -m unittest tests.test_ec022_readonly tests.test_ec022_indec_salarios tests.test_ec022_cvs tests.test_ec022_bcra_hipotecarios tests.test_ec022_ripte_historico tests.test_ec022_ipc tests.test_ec022_fuentes_historicas tests.test_ec022_writer_draft tests.test_ec022_bcra_uva -v
        if ($LASTEXITCODE -ne 0) { throw 'Unit tests failed.' }
        $env:EC022_DISPOSABLE_TEST_CLUSTER='yes'; $env:EC022_TEST_DSN=$dbUrl
        & $py -m tests.ec022_writer_integration
        if ($LASTEXITCODE -ne 0) { throw 'Writer integration test failed.' }
        & $py tests/ec022_concurrent_writer.py
        if ($LASTEXITCODE -ne 0) { throw 'Concurrent writer test failed.' }
    } finally { Pop-Location }
    Write-Host 'EC-022 existing-lab validation passed. No other stack was touched.'
    if ($Publicar) {
        $branch=(& git -C $repo branch --show-current | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or $branch -ne 'ec022-hipotecarios-readonly') {
            throw 'Refusing to publish from an unexpected branch.'
        }
        Write-Host 'Publishing the verified branch; Git will reject non-fast-forward updates.'
        & git -C $repo push origin ec022-hipotecarios-readonly
        if ($LASTEXITCODE -ne 0) { throw 'Git push failed; see the Git error above.' }
    }
} finally {
    $env:SUPABASE_EXPERIMENTAL_STACK=$oldExperimental
    $env:PGPASSWORD=$oldPassword
    $env:EC022_TEST_DSN=$oldDsn
    $env:EC022_DISPOSABLE_TEST_CLUSTER=$oldDisposable
}
