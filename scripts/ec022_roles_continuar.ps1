#requires -Version 7.0
<# Diagnose and repair only the existing EC-022 stack. No init, start, reset, stop, destroy,
   link, remote commands, or changes to another stack. #>
param([Parameter(Mandatory=$true)][string]$RepoPath, [switch]$Publicar)
$ErrorActionPreference = 'Stop'
$repo=(Resolve-Path -LiteralPath $RepoPath).Path
$id='ec022lab08f2e7bbd3db'
$lab=Join-Path (Split-Path $repo -Parent) $id
$config=Join-Path $lab 'supabase/config.jsonc'
$prototype=Join-Path $repo 'docs/ec022/prototipo_almacenamiento.sql'
$sqlTests=Join-Path $repo 'tests/ec022_almacenamiento_aislado.sql'
$diagnostic=Join-Path $repo 'tests/ec022_diagnostico_acl.sql'
$aclCandidate=Join-Path $repo 'docs/ec022/correccion_acl_incremental.sql'
$serviceCandidate=Join-Path $repo 'docs/ec022/correccion_service_role.sql'
$migration=Join-Path $lab 'supabase/migrations/20261127232951_ec022_lab_candidate.sql'
foreach ($path in @($config,$prototype,$sqlTests,$diagnostic,$aclCandidate,$serviceCandidate,$migration)) {
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
$oldSeries=$env:EC022_TEST_SERIES
$temporaryGrants=[System.Collections.Generic.List[object]]::new()
$base=$null
$readyToPublish=$false
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
    $currentHash=(& git -C $repo hash-object $migration).Trim()
    $correctedHash=(& git -C $repo hash-object $prototype).Trim()
    if (-not ($state.history -eq 1 -and $currentHash -eq $correctedHash -and $state.roles -eq 4 -and $state.schema -and $state.series -and $state.observaciones -and $state.aprobaciones)) {
        throw 'Original applied migration, file, or objects are inconsistent; no repair was attempted.'
    }
    Write-Host 'Diagnosing effective ACLs and role memberships before any correction:'
    & $psql @base -f $diagnostic
    if ($LASTEXITCODE -ne 0) { throw 'Privilege diagnostic failed; see the error above.' }
    $legacy=(& $psql @base -t -A -c "select json_build_object('series',(select count(*) from public.ec022_series where serie='test'),'observations',(select count(*) from public.ec022_observaciones where serie='test'),'approvals',(select count(*) from public.ec022_aprobaciones where serie='test'))::text;" | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect the prior synthetic fixture.' }
    Write-Host "Prior synthetic fixture (preserved): $legacy"

    $migrationsDir=Join-Path $lab 'supabase/migrations'
    $files=@(Get-ChildItem -LiteralPath $migrationsDir -Filter '*.sql')
    $unknown=@($files | Where-Object { $_.Name -ne '20261127232951_ec022_lab_candidate.sql' -and $_.Name -notmatch '^\d{14}_ec022_(acl_correction|service_role_fix)\.sql$' })
    $fixes=@($files | Where-Object { $_.Name -match '^\d{14}_ec022_acl_correction\.sql$' })
    if ($unknown.Count -ne 0 -or $fixes.Count -ne 1) { throw 'Expected exactly the previously applied ACL migration and no unexpected files.' }
    $fixHash=(& git -C $repo hash-object $fixes[0].FullName).Trim()
    $expectedHash=(& git -C $repo hash-object $aclCandidate).Trim()
    if ($fixHash -ne $expectedHash) { throw 'Incremental migration differs from the reviewed candidate.' }
    $fixVersion=$fixes[0].Name.Substring(0,14)
    if ([string]::CompareOrdinal($fixVersion,'20261127232951') -le 0) { throw 'Incremental migration version is not newer than the applied migration.' }
    $fixHistory=(& $psql @base -t -A -c "select count(*) from supabase_migrations.schema_migrations where version='$fixVersion';" | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $fixHistory -notin @('0','1')) { throw 'Unexpected incremental migration history.' }
    if ($fixHistory -ne '1') { throw 'Prior ACL correction is not recorded; refusing to repeat it.' }
    Write-Host 'Prior ACL correction is recorded and will not be repeated.'
    Write-Host 'Diagnosing effective ACLs after correction:'
    & $psql @base -f $diagnostic
    if ($LASTEXITCODE -ne 0) { throw 'Post-correction privilege diagnostic failed.' }

    $serviceValue=(& $psql @base -t -A -c "select has_function_privilege('service_role','public.ec022_ingestar_observacion(text,date,text,numeric,text,timestamptz,date)','execute');" | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $serviceValue -notin @('t','f')) { throw 'Could not inspect service_role EXECUTE.' }
    Write-Host "service_role EXECUTE on exclusive writer: $serviceValue"
    if ($serviceValue -eq 't') {
        $serviceFiles=@(Get-ChildItem -LiteralPath $migrationsDir -Filter '*_ec022_service_role_fix.sql')
        if ($serviceFiles.Count -gt 1) { throw 'More than one service-role correction exists.' }
        if ($serviceFiles.Count -eq 0) {
            & npx.cmd --yes supabase@3.4.0 migration new ec022_service_role_fix --workdir $lab
            if ($LASTEXITCODE -ne 0) { throw 'Could not generate the service-role migration.' }
            $serviceFiles=@(Get-ChildItem -LiteralPath $migrationsDir -Filter '*_ec022_service_role_fix.sql')
            if ($serviceFiles.Count -ne 1) { throw 'Unexpected service-role migration count.' }
            Copy-Item -LiteralPath $serviceCandidate -Destination $serviceFiles[0].FullName
        }
        if ((& git -C $repo hash-object $serviceFiles[0].FullName).Trim() -ne (& git -C $repo hash-object $serviceCandidate).Trim()) { throw 'Service-role migration content differs from the reviewed candidate.' }
        $serviceVersion=$serviceFiles[0].Name.Substring(0,14)
        if ([string]::CompareOrdinal($serviceVersion,$fixVersion) -le 0) { throw 'Service-role migration version is not incremental.' }
        $serviceHistory=(& $psql @base -t -A -c "select count(*) from supabase_migrations.schema_migrations where version='$serviceVersion';" | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or $serviceHistory -ne '0') { throw 'Service-role migration history is inconsistent with its effective privilege.' }
        & npx.cmd --yes supabase@3.4.0 migration up --workdir $lab --stack $id
        if ($LASTEXITCODE -ne 0) { throw 'Service-role correction failed; see the SQL error above.' }
    }
    & $psql @base -f $diagnostic
    if ($LASTEXITCODE -ne 0) { throw 'Final privilege diagnostic failed.' }

    # Exercise the real loopback REST endpoint before any test-role grants.
    $apiUrl=[string]$status.env.API_URL
    $anonKey=[string]$status.env.ANON_KEY
    try { $apiUri=[uri]$apiUrl } catch { throw 'Invalid local API URL.' }
    if (-not $anonKey -or $apiUri.Host -notin @('127.0.0.1','localhost','::1') -or $apiUri.Scheme -ne 'http') { throw 'Unexpected local REST endpoint.' }
    $headers=@{apikey=$anonKey; Authorization="Bearer $anonKey"}
    try { Invoke-RestMethod -Uri "$apiUrl/rest/v1/ec022_series?select=serie&limit=1" -Headers $headers -MaximumRedirection 0 | Out-Null }
    catch { throw "Local REST service is unavailable: $($_.Exception.Message)" }
    Write-Host 'Local REST endpoint responded successfully.'

    # Grant SET only where absent. Record whether the self-granted edge already
    # existed, so finally restores its exact SET state rather than removing it.
    $roleQuery="select json_agg(json_build_object('name',r.rolname,'can_set',pg_has_role(current_user,r.oid,'SET'),'can_admin',pg_has_role(current_user,r.oid,'MEMBER WITH ADMIN OPTION'),'self_edge',exists(select 1 from pg_auth_members m where m.roleid=r.oid and m.member=(select oid from pg_roles where rolname=current_user) and m.grantor=(select oid from pg_roles where rolname=current_user)),'self_admin',(select m.admin_option from pg_auth_members m where m.roleid=r.oid and m.member=(select oid from pg_roles where rolname=current_user) and m.grantor=(select oid from pg_roles where rolname=current_user)),'self_inherit',(select m.inherit_option from pg_auth_members m where m.roleid=r.oid and m.member=(select oid from pg_roles where rolname=current_user) and m.grantor=(select oid from pg_roles where rolname=current_user))) order by r.rolname)::text from pg_roles r where r.rolname in ('anon','ec022_ingestor','ec022_validador');"
    $roleJson=(& $psql @base -t -A -c $roleQuery | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect test role privileges.' }
    $roleStates=@(($roleJson | ConvertFrom-Json) | ForEach-Object { $_ })
    if ($roleStates.Count -ne 3) { throw 'Expected test roles are missing.' }
    foreach ($stateItem in $roleStates) {
        if (-not $stateItem.can_set -and -not $stateItem.can_admin) {
            throw "Cannot SET or administer test role $($stateItem.name); no test-role grants were made."
        }
    }
    foreach ($stateItem in $roleStates) {
        Write-Host ("Test role {0}: SET already allowed={1}, preexisting self-grant={2}" -f $stateItem.name,$stateItem.can_set,$stateItem.self_edge)
        if (-not $stateItem.can_set) {
            $roleName=[string]$stateItem.name
            if ($roleName -notin @('anon','ec022_ingestor','ec022_validador')) { throw 'Unexpected role name.' }
            $grantSql=if ($stateItem.self_edge) { "grant `"$roleName`" to current_user with set true;" } else { "grant `"$roleName`" to current_user with set true, inherit false;" }
            & $psql @base -c $grantSql
            if ($LASTEXITCODE -ne 0) { throw "Cannot grant temporary SET for test role $roleName; inspect ADMIN OPTION." }
            $temporaryGrants.Add([pscustomobject]@{Name=$roleName; Existing=[bool]$stateItem.self_edge; Admin=$stateItem.self_admin; Inherit=$stateItem.self_inherit})
        }
    }

    # Each execution gets a fresh synthetic series. Existing partial or prior
    # fixtures are neither overwritten nor deleted.
    $testSeries='ec022_test_'+[guid]::NewGuid().ToString('N').Substring(0,12)
    $testSql=Join-Path $lab ($testSeries+'.sql')
    if (Test-Path -LiteralPath $testSql) { throw 'Generated test file already exists.' }
    $scriptText=(Get-Content -LiteralPath $sqlTests -Raw).Replace("'test'","'$testSeries'")
    [System.IO.File]::WriteAllText($testSql,$scriptText,[System.Text.UTF8Encoding]::new($false))
    & $psql @base -f $testSql
    if ($LASTEXITCODE -ne 0) { throw 'SQL integration test failed; see the database error above.' }
    & $psql @base -c "set role ec022_validador; insert into public.ec022_aprobaciones (serie,periodo,fuente_sha256,accion,motivo) values ('$testSeries','2020-01-01',repeat('b',64),'aprobar','API test');"
    if ($LASTEXITCODE -ne 0) { throw 'Could not prepare the local REST fixture.' }
    try { $rows=@((Invoke-RestMethod -Uri "$apiUrl/rest/v1/ec022_observaciones?select=serie,valor&serie=eq.$testSeries" -Headers $headers -MaximumRedirection 0) | ForEach-Object { $_ }) }
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
        $env:EC022_DISPOSABLE_TEST_CLUSTER='yes'; $env:EC022_TEST_DSN=$dbUrl; $env:EC022_TEST_SERIES=$testSeries
        & $py -m tests.ec022_writer_integration
        if ($LASTEXITCODE -ne 0) { throw 'Writer integration test failed.' }
        & $py tests/ec022_concurrent_writer.py
        if ($LASTEXITCODE -ne 0) { throw 'Concurrent writer test failed.' }
    } finally { Pop-Location }
    Write-Host 'EC-022 existing-lab validation passed. No other stack was touched.'
    $readyToPublish=$true
} finally {
    $cleanupFailures=[System.Collections.Generic.List[string]]::new()
    if ($base) {
        foreach ($grant in $temporaryGrants) {
            $roleName=$grant.Name
            $revokeSql=if ($grant.Existing) { "revoke set option for `"$roleName`" from current_user;" } else { "revoke `"$roleName`" from current_user;" }
            & $psql @base -c $revokeSql
            if ($LASTEXITCODE -ne 0) { $cleanupFailures.Add($roleName); continue }
            $verifyQuery="select json_build_object('can_set',pg_has_role(current_user,'$roleName','SET'),'edge',exists(select 1 from pg_auth_members m where m.roleid='$roleName'::regrole and m.member=(select oid from pg_roles where rolname=current_user) and m.grantor=(select oid from pg_roles where rolname=current_user)),'admin',(select m.admin_option from pg_auth_members m where m.roleid='$roleName'::regrole and m.member=(select oid from pg_roles where rolname=current_user) and m.grantor=(select oid from pg_roles where rolname=current_user)),'inherit',(select m.inherit_option from pg_auth_members m where m.roleid='$roleName'::regrole and m.member=(select oid from pg_roles where rolname=current_user) and m.grantor=(select oid from pg_roles where rolname=current_user)))::text;"
            $verifyText=(& $psql @base -t -A -c $verifyQuery | Out-String).Trim()
            if ($LASTEXITCODE -ne 0) { $cleanupFailures.Add($roleName); continue }
            $verified=$verifyText | ConvertFrom-Json
            if ($verified.can_set -or [bool]$verified.edge -ne $grant.Existing -or ($grant.Existing -and ($verified.admin -ne $grant.Admin -or $verified.inherit -ne $grant.Inherit))) { $cleanupFailures.Add($roleName) }
        }
    }
    $env:SUPABASE_EXPERIMENTAL_STACK=$oldExperimental
    $env:PGPASSWORD=$oldPassword
    $env:EC022_TEST_DSN=$oldDsn
    $env:EC022_DISPOSABLE_TEST_CLUSTER=$oldDisposable
    $env:EC022_TEST_SERIES=$oldSeries
    if ($cleanupFailures.Count -gt 0) { throw "Temporary SET cleanup failed for: $($cleanupFailures -join ', '). Inspect before further use." }
}
if ($Publicar -and $readyToPublish) {
    $branch=(& git -C $repo branch --show-current | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $branch -ne 'ec022-hipotecarios-readonly') { throw 'Refusing to publish from an unexpected branch.' }
    Write-Host 'Publishing the verified branch; Git will reject non-fast-forward updates.'
    & git -C $repo push origin ec022-hipotecarios-readonly
    if ($LASTEXITCODE -ne 0) { throw 'Git push failed; see the Git error above.' }
}
