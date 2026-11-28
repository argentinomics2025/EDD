#requires -Version 7.0
<# Local-only EC-022 laboratory. It never links to a hosted project and never
   stops or destroys any stack. It creates a fresh named stack and directory.
   Local connection details are kept in process memory, not printed or saved. #>
param([Parameter(Mandatory=$true)][string]$RepoPath)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path -LiteralPath $RepoPath).Path
$prototype = Join-Path $repo 'docs/ec022/prototipo_almacenamiento.sql'
$sqlTests = Join-Path $repo 'tests/ec022_almacenamiento_aislado.sql'
$concurrent = Join-Path $repo 'tests/ec022_concurrent_writer.py'
foreach ($path in @($prototype,$sqlTests,$concurrent)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing required EC-022 file: $path" }
}
foreach ($cmd in @('docker','npx.cmd','python')) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw "Missing executable: $cmd" }
}
$psql = (Get-Command psql.exe -ErrorAction SilentlyContinue).Source
if (-not $psql -and (Test-Path 'C:/Program Files/PostgreSQL/17/bin/psql.exe')) {
    $psql = 'C:/Program Files/PostgreSQL/17/bin/psql.exe'
}
if (-not $psql) { throw 'psql.exe is required to run the SQL integration tests.' }
& docker version --format '{{.Server.Version}}'
if ($LASTEXITCODE -ne 0) { throw 'Docker daemon is not reachable; no laboratory was created.' }

$id = 'ec022lab' + [guid]::NewGuid().ToString('N').Substring(0,12)
$lab = Join-Path (Split-Path $repo -Parent) $id
if (Test-Path -LiteralPath $lab) { throw 'Laboratory path unexpectedly exists.' }
New-Item -ItemType Directory -Path $lab | Out-Null
$oldExperimental = $env:SUPABASE_EXPERIMENTAL_STACK
$oldPassword = $env:PGPASSWORD
$oldDsn = $env:EC022_TEST_DSN
$oldDisposable = $env:EC022_DISPOSABLE_TEST_CLUSTER
try {
    $env:SUPABASE_EXPERIMENTAL_STACK = '1'
    Write-Host "Creating isolated local EC-022 laboratory: $id"
    & npx.cmd --yes supabase@3.4.0 init --workdir $lab
    if ($LASTEXITCODE -ne 0) { throw 'Supabase init failed.' }
    $config = Join-Path $lab 'supabase/config.jsonc'
    if (-not (Test-Path -LiteralPath $config)) { throw 'Local configuration was not created.' }
    # Explicit unique stack and root: never select or stop ec021-restore-test.
    $start = (& npx.cmd --yes supabase@3.4.0 stack start --workdir $lab --stack $id --runtime docker --output-format json | Out-String)
    if ($LASTEXITCODE -ne 0) { throw 'Local Supabase start failed; see Docker Desktop for the isolated stack state.' }
    $status = $start | ConvertFrom-Json
    $dbUrl = [string]$status.env.DB_URL
    if (-not $dbUrl) { throw 'Local stack did not provide DB_URL; refusing to run SQL.' }
    try { $uri = [uri]$dbUrl } catch { throw 'Invalid local database URL.' }
    if ($uri.Host -notin @('127.0.0.1','localhost','::1') -or $uri.Port -le 0) {
        throw 'Database URL is not loopback; refusing to continue.'
    }
    $userInfo = $uri.UserInfo.Split(':',2)
    if ($userInfo.Count -ne 2 -or [uri]::UnescapeDataString($userInfo[0]) -ne 'postgres') {
        throw 'Unexpected local database identity; refusing to continue.'
    }
    $env:PGPASSWORD = [uri]::UnescapeDataString($userInfo[1])
    $dbName = $uri.AbsolutePath.TrimStart('/')
    if ($dbName -ne 'postgres') { throw 'Unexpected local database name.' }

    # Generate the migration with the CLI in this isolated root, then apply only
    # to its explicitly named local stack. The prototype remains unapproved.
    & npx.cmd --yes supabase@3.4.0 migration new ec022_lab_candidate --workdir $lab
    if ($LASTEXITCODE -ne 0) { throw 'Could not create local migration file.' }
    $migration = @(Get-ChildItem -LiteralPath (Join-Path $lab 'supabase/migrations') -Filter '*_ec022_lab_candidate.sql')
    if ($migration.Count -ne 1) { throw 'Migration candidate is not unique.' }
    Copy-Item -LiteralPath $prototype -Destination $migration[0].FullName
    & npx.cmd --yes supabase@3.4.0 migration up --workdir $lab --stack $id
    if ($LASTEXITCODE -ne 0) { throw 'Candidate migration failed on the local EC-022 stack.' }
    Write-Host 'Local candidate migration applied; running SQL permissions and rollback tests.'
    & $psql -X -h $uri.Host -p $uri.Port -U postgres -d postgres -v ON_ERROR_STOP=1 -f $sqlTests
    if ($LASTEXITCODE -ne 0) { throw 'SQL integration test failed.' }
    & $psql -X -h $uri.Host -p $uri.Port -U postgres -d postgres -v ON_ERROR_STOP=1 -c "set role ec022_validador; insert into public.ec022_aprobaciones (serie,periodo,fuente_sha256,accion,motivo) values ('test','2020-01-01',repeat('b',64),'aprobar','API test');"
    if ($LASTEXITCODE -ne 0) { throw 'Could not prepare local API test.' }
    $apiUrl = [string]$status.env.API_URL
    $anonKey = [string]$status.env.ANON_KEY
    try { $apiUri = [uri]$apiUrl } catch { throw 'Invalid local API URL.' }
    if (-not $anonKey -or $apiUri.Host -notin @('127.0.0.1','localhost','::1') -or $apiUri.Scheme -ne 'http') {
        throw 'Missing local anon key or non-loopback API; refusing API test.'
    }
    $headers = @{ apikey = $anonKey; Authorization = "Bearer $anonKey" }
    try {
        $publicRows = @((Invoke-RestMethod -Uri "$apiUrl/rest/v1/ec022_observaciones?select=serie,valor&serie=eq.test" -Headers $headers -MaximumRedirection 0) | ForEach-Object { $_ })
    } catch { throw "Local public read API failed: $($_.Exception.Message)" }
    if ($publicRows.Count -ne 1 -or [decimal]$publicRows[0].valor -ne 101) {
        throw 'Local API did not return exactly the approved edition.'
    }
    $blocked = $false
    try {
        Invoke-RestMethod -Uri "$apiUrl/rest/v1/ec022_aprobaciones?select=evento" -Headers $headers -MaximumRedirection 0 | Out-Null
    } catch {
        if ([int]$_.Exception.Response.StatusCode -in @(401,403,404)) { $blocked = $true }
    }
    if (-not $blocked) { throw 'Local public API unexpectedly exposed approvals.' }
    Write-Host 'Local REST API returned the approved edition and denied approval-table access.'

    $venv = Join-Path $lab '.venv'
    & python -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the isolated Python environment.' }
    $py = Join-Path $venv 'Scripts/python.exe'
    & $py -m pip install -r (Join-Path $repo 'requirements-ec022.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Could not install pinned Python dependencies.' }
    Push-Location $repo
    try {
        & $py -m unittest tests.test_ec022_readonly tests.test_ec022_indec_salarios tests.test_ec022_cvs tests.test_ec022_bcra_hipotecarios tests.test_ec022_ripte_historico tests.test_ec022_ipc tests.test_ec022_fuentes_historicas tests.test_ec022_writer_draft tests.test_ec022_bcra_uva -v
        if ($LASTEXITCODE -ne 0) { throw 'Python unit tests failed.' }
        $env:EC022_DISPOSABLE_TEST_CLUSTER = 'yes'
        $env:EC022_TEST_DSN = $dbUrl
        & $py -m tests.ec022_writer_integration
        if ($LASTEXITCODE -ne 0) { throw 'Transactional writer test failed.' }
        & $py $concurrent
        if ($LASTEXITCODE -ne 0) { throw 'Concurrent writer test failed.' }
    } finally { Pop-Location }
    Write-Host "EC-022 local tests passed. Lab directory: $lab"
    Write-Host "The isolated stack $id remains running; no other stack was stopped or deleted."
} finally {
    $env:SUPABASE_EXPERIMENTAL_STACK = $oldExperimental
    $env:PGPASSWORD = $oldPassword
    $env:EC022_TEST_DSN = $oldDsn
    $env:EC022_DISPOSABLE_TEST_CLUSTER = $oldDisposable
}
