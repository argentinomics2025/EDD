# EC-016 — contratos y alcance del laboratorio

**NO AUTORIZADO PARA EJECUCIÓN. NO APTO PARA PRODUCCIÓN.**
Procedimiento y auditoría vigente: [ec-016-hardening.md](ec-016-hardening.md).

El arnés usa datos sintéticos de 2010 y llama directamente al SDK PostgREST.
No invoca los robots ni elimina su bloqueo incondicional de escrituras.
El esquema es una fixture descartable, no una migración productiva.

| Tabla | Clave para on_conflict | Tipos y limitaciones |
|---|---|---|
| datos_comex | fecha | date primer día; 13 campos económicos numeric; nota extra para comprobar conservación |
| socios_comerciales | fecha_informe,pais | período textual; importes numeric completos obligatorios; rankings parciales aún bloqueados para persistencia |
| comex_rubros | fecha_informe,tipo_flujo,rubro_principal,subrubro | período textual, flujo enumerado, valor numeric no negativo |

Las tres claves requieren restricciones UNIQUE reales; hay índices adicionales
sobre nombres normalizados para rechazar colisiones. NOT NULL y CHECK rechazan
claves/importes inválidos. La conciliación estricta de la fixture sólo se aplica
a datos sintéticos: no impone una regla económica nueva a las fuentes oficiales.

Roles sintéticos reader/writer sin BYPASSRLS; authenticator NOINHERIT. Sólo
SELECT/INSERT, RLS por scope/run/owner; sin UPDATE/DELETE. El administrador es
exclusivo de la fixture y comprueba la identidad antes de devolver su conexión.
Triggers rechazan mutaciones y auditan inserciones dentro de la transacción.

Las 11 pruebas de integración preparadas cubren:

1. Reejecución, históricos y columnas omitidas no predeterminadas.
2. CHECK, rollback completo y auditoría sin cambios.
3. Ausencia de UNIQUE: 42P10 y cero cambios.
4. Claves nulas y países parciales: 23502, sin inventar ceros.
5. Colisiones normalizadas: 23505.
6. RLS, lector/anónimo y UPDATE/DELETE: 42501.
7. Respuesta perdida tras commit y reintento idempotente.
8. Inserciones concurrentes con importes diferentes: primera inserción gana.
9. Precisión NUMERIC y trigger administrativo: P0001.
10. Corpus de normalización de países.
11. Repetición concurrente idéntica: una fila y una auditoría.

Snapshots de filas y auditoría comparan JSON textual ordenado desde PostgreSQL,
no sólo conteos. No se presume atomicidad entre solicitudes/robots distintos.
No ejecutadas: faltan autorización, infraestructura y comprobación real de
SQL/SDK. Interrupción real de proceso, deadlock/serialization y backoff requieren
un perfil posterior; el timeout actual pierde una respuesta ya confirmada.
