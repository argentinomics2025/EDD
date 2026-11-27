# EC-022.1 — Continuación de históricos y controles, 27/11/2026

Estado: NO APTO para producción o cierre. Se conserva la evidencia anterior y el commit inicial 47214626bc2ebdf224eb2e72cb1acac8286e06f3.

## Históricos adicionales

- El XLS oficial INDEC `https://sitioanterior.indec.gob.ar/ftp/cuadros/sociedad/serie_cvs_diarios_2012.xls` se leyó como serie independiente, base abril 2012=100. 5.051 días, 01/01/2002–30/10/2015; SHA-256 `9810bacfcb46900de3ee4897e992ac8a315120ba57d85cf8cbb42359bb11666c`. El archivo reciente de CVS registrado comienza 01/11/2015; 31/10/2015 no está en ninguno de estos dos tramos. No se fabricó el dato ni se ha validado un empalme entre bases.
- El XLS oficial `https://sitioanterior.indec.gob.ar/ftp/cuadros/sociedad/serie_is_2012.xls` se leyó como serie histórica independiente de nivel general, base abril 2012=100. 169 meses, 10/2001–10/2015; SHA-256 `edbacc4257884e9c74c28e25c7f3b615b7fe215c73281cbf1e0dd57831e2e7bc`. No debe confundirse con la serie total base octubre 2016=100 ni suponerse continuidad metodológica sin validación.
- El PDF primario de Seguridad Social `https://www.argentina.gob.ar/sites/default/files/ripte_septiembre_2026-mdch.pdf` contiene 387 meses desde julio 1994 hasta septiembre 2026 y variaciones publicadas. SHA-256 `8a1a04c0f48b289d58ae085a6dfaeb51a747afb5366035178759e439e5ceedd7`. La columna de variación presenta guiones para julio 1994 y julio 2000; se conservan como nulos, sin inventar cifras. Las demás variaciones se contrastaron con los niveles del propio PDF con tolerancia de 0,15 puntos porcentuales.
- El PDF y CSV oficial de datos.gob.ar tienen una discrepancia nominal en noviembre de 2017: PDF $26.177,33 y CSV $26.177,83. Los otros 386 niveles coinciden. La diferencia debe ser revisada y versionada, no resuelta por fecha de descarga ni modificando la fuente.

## Verificación local y límites

- 22 pruebas unitarias aprobadas, incluidas las 19 previas. Se probaron los tres archivos originales reales y se conservaron sus huellas. El resultado depende del formato actual del PDF; un cambio de formato falla de forma explícita.
- En PostgreSQL 17 aislado se repitieron los controles del prototipo y un escenario concurrente con dos aprobaciones para el mismo período. Se añadió bloqueo transaccional por serie/período antes de asignar el orden efectivo de aprobación. Este ensayo no certifica otros niveles de aislamiento, fallos de procesos ni la configuración Supabase.
- Se generó mediante `supabase migration new` un archivo en un directorio local de borrador, fuera del árbol de migraciones del repositorio, y se copió en él el prototipo SQL. No es una migración lista para producción; falta terminar el diseño y ejecutar el conjunto completo de pruebas, incluidas colisiones de idempotencia, permisos reales, rollback de esquema con datos y validación Supabase aislada. No se aplicó nada a producción.
- La rama remota permanecía en 90cd65b. El `gh auth status` de esta sesión devolvió HTTP 401 y el helper Git no pudo arrancar por `NtCreateDirectoryObject ... 0xC0000022`; no se publicó la rama ni se creó PR. El ejecutable instalado `C:/Program Files/Git/cmd/git.exe` informa 2.56.1.windows.1, pero el PATH de este proceso selecciona el Git incluido en Codex.
- Sin rama Supabase aislada existente y sin presupuesto/cupo de Actions verificado, no se activaron consumos adicionales, automatización ni cargas. Quedan pendientes datos productivos, contrato operativo probado y verificación económica restante.
