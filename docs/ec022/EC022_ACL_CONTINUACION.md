# EC-022 — Diagnóstico y corrección incremental de ACL

La prueba fallida verifica cuatro condiciones: EXECUTE de `anon` y de `authenticated` sobre `public.ec022_ingestar_observacion` debe ser falso; EXECUTE de `ec022_ingestor` sobre esa función y de `anon` sobre `ec022_privado.es_publicada` debe ser verdadero. El mensaje original no indica cuál condición falló. Hasta consultar el laboratorio no se puede atribuir el error a un rol o grant concreto. Un grant predeterminado explícito, PUBLIC o una membresía heredada son hipótesis, no resultados verificados.

`tests/ec022_diagnostico_acl.sql` imprime esas cuatro condiciones, propietario y ACL de cada función, privilegios predeterminados para funciones y árbol de membresías de los roles relevantes. `scripts/ec022_acl_continuar.ps1` ejecuta ese diagnóstico antes de cambiar nada y lo repite después. Verifica que la migración original esté registrada y el archivo corresponda al candidato aplicado, que existan los objetos esperados y que no exista la fixture de prueba. No sobrescribe la migración original ni borra objetos o datos.

El script crea mediante Supabase CLI una **migración incremental** en el directorio del laboratorio existente. El SQL candidato `correccion_acl_incremental.sql` verifica previamente que los propietarios sean los roles NOLOGIN/NOBYPASSRLS previstos y que ambas funciones sigan siendo SECURITY DEFINER con búsqueda fijada. Otorga SET temporal al ejecutor únicamente para asumir cada propietario y ajustar sus propios ACL: retira PUBLIC, anon y authenticated del escritor y otorga EXECUTE al ingestor; retira PUBLIC de la consulta y otorga EXECUTE a anon/authenticated. Luego revoca el SET temporal. Si un permiso inseguro persiste, por ejemplo por una membresía heredada, falla transaccionalmente sin retirar permisos de otros roles. La migración conserva datos, políticas, roles y la migración original.

En PostgreSQL 17 aislado con ejecutor no superusuario `CREATEROLE`, se simuló un grant explícito indebido de anon/authenticated al escritor y falta de EXECUTE de anon al lector: el candidato corrigió ambos y dejó las cuatro comprobaciones en `f, f, t, t`. Una segunda prueba con EXECUTE heredado por anon falló con `EC022_ACL_STILL_UNSAFE` y confirmó rollback; no revocó la membresía ajena. Estas simulaciones no identifican el permiso real del laboratorio Supabase. Las 28 pruebas unitarias previas siguen aprobadas; las pruebas SQL, REST, escritor y concurrencia del laboratorio real siguen pendientes hasta ejecutar el script.

El script no inicia, detiene, reinicia, recrea ni borra ningún stack, y no enlaza ningún proyecto remoto. Con `-Publicar` envía la rama solo si pasan las pruebas. Se muestran los errores relevantes; el JSON de estado que contiene credenciales locales permanece en memoria. Ante error, compartir el diagnóstico de ACL y el primer error, excluyendo contraseñas, claves y URLs con credenciales.

```powershell
pwsh -NoProfile -File 'C:\Users\domin\Documents\Codex\2026-11-27\argus-econom-a-criolla-ec-022\work\EDD\scripts\ec022_acl_continuar.ps1' -RepoPath 'C:\Users\domin\Documents\Codex\2026-11-27\argus-econom-a-criolla-ec-022\work\EDD' -Publicar
```

Ni la corrección ni la publicación de producción quedan autorizadas por esta prueba local. No se cambia EC-021.
