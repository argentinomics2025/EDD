# Continuación del laboratorio EC-022 existente

El script `scripts/ec022_continuar_lab.ps1` usa exclusivamente el directorio y el stack `ec022lab08f2e7bbd3db`. No crea, inicia, detiene, elimina ni reinicia stacks; no enlaza Supabase remoto. Rechaza rutas no locales, identidades inesperadas, migraciones alteradas y marcadores de enlace remoto. Antes de escribir examina la versión de la migración y los objetos/roles EC-022. Si encuentra objetos parciales sin historial, una versión o un archivo inesperado, o una fixture de pruebas previa, se detiene y no borra ni reemplaza objetos o datos. Si el archivo es el original, conserva una copia antes de actualizarlo. Si el candidato corregido ya se aplicó, lo verifica antes de ejecutar pruebas.

El ajuste del usuario `config.jsonc` se conserva en el script original. Las salidas de error de Docker, CLI, SQL y pruebas ya no se descartan; la respuesta JSON de estado que contiene claves locales se mantiene en memoria, sin imprimirse. Compartir solo el primer error y quitar credenciales si aparecieran en un diagnóstico externo.

El candidato ahora otorga temporalmente `SET TRUE, INHERIT FALSE` a cada rol propietario solo alrededor del `ALTER FUNCTION ... OWNER`, y revoca el otorgamiento al terminar. Los REVOKE/GRANT de EXECUTE se realizan antes de transferir cada función. Los propietarios mantienen `NOLOGIN`, `NOBYPASSRLS`, búsqueda fijada y políticas RLS acotadas. PostgreSQL puede conservar la membresía automática del creador con `ADMIN` pero sin `SET` ni `INHERIT`; la migración verifica que el ejecutor no superusuario carezca de privilegios efectivos `SET` y `USAGE` después de revocar los otorgamientos temporales. El administrador de migraciones conserva su capacidad inherente de administrar roles creados, y no es un rol de aplicación.

Se ensayó el candidato completo en PostgreSQL 17 aislado utilizando un ejecutor `LOGIN CREATEROLE` sin superusuario, seguido de pruebas de RLS, permisos de función, idempotencia, revisiones y rollback. Se verificaron `anon` sin EXECUTE del escritor, propietarios sin LOGIN/BYPASSRLS/SUPERUSER y que el ejecutor no pudiera heredar ni asumir los dos roles propietarios. Las 28 pruebas unitarias siguen aprobadas. Estos ensayos no sustituyen la ejecución del laboratorio Supabase local ni prueban su REST.

Ejecución en PowerShell 7:

```powershell
pwsh -NoProfile -File 'C:\Users\domin\Documents\Codex\2026-11-27\argus-econom-a-criolla-ec-022\work\EDD\scripts\ec022_continuar_lab.ps1' -RepoPath 'C:\Users\domin\Documents\Codex\2026-11-27\argus-econom-a-criolla-ec-022\work\EDD' -Publicar
```

Una falla deja visible el error correspondiente. `-Publicar` envía la rama existente a GitHub solo después de superar las pruebas; Git rechazará una actualización que no sea fast-forward. El script evita una reparación automática destructiva si detecta cambios parciales; en ese caso debe revisarse el resultado del preflight antes de decidir una recuperación. No se autoriza ninguna aplicación productiva hasta completar y revisar la validación.
