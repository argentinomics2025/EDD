# EC-007.3 — Dictamen de aceptación técnica parcial (04/11/2026)

**Resultado:** PREPARACIÓN OFFLINE VALIDADA; **NO APTO PARA MERGE, INGESTA NI PUBLICACIÓN**.

## Evidencia reproducible

Se ejecutó una única batería local con Pytest 9.0.2 sobre nueve módulos de prueba: **133 tests PASS + 54 subtests PASS**, sin fallos, en 1.42 s. Incluye 59 de validación financiera inicial, 33 del motor/SQL estático, 25 de contratos oficiales e integración sintética, 12 del protocolo aislado y cuatro de seguridad editorial. Esta batería NO equivale a CI sobre HEAD remoto ni ejecución funcional de la base de datos.

El XLSX aportado por el usuario tiene SHA-256 `0125ff566582063502b4b11f07e0dbcdc0945530b24d80c73ef074e8ccb54528`. La discrepancia GD35 entre A.1!F7/G7 y el Anexo del Decreto 701/2020 está documentada en `docs/EC0073_contratos_2026_09_30_conflicto_GD35.md`. Los flujos contractuales son offline y no incluyen precio observado, intereses corridos verificados, ni fecha real de liquidación.

## Gates antes de habilitar producción

| Gate | Criterio de aceptación | Situación |
|---|---|---|
| Licencia/captura | autorización escrita para obtener, conservar, procesar y redistribuir cotizaciones; acceso autorizado y muestra real con timestamp y unidad | **BLOQUEADO:** Rava sin respuesta |
| Mercado | validación por cada una de las 18 especies de moneda/mercado/unidad, precio clean/dirty, fecha de liquidación, ajuste feriados y procedencia | **NO HOMOLOGADO** |
| Cálculo | diferencias TIR/duration conciliadas contra fuente independiente para cada bono, con las convenciones exactas | **SOLO ENSAYO MATEMÁTICO** |
| Histórico | ejecutar DDL y ensayo sintético en PostgreSQL completamente DESCARTABLE; comprobar grants, RLS FORCE, idempotencia, append-only, revisiones y rollback | **SIN PG REAL** |
| Seguridad | revisión de RBAC/roles de inserción, no utilizar BYPASSRLS fuera del laboratorio, zero grants públicos | **SOLO ESTÁTICO** |
| Integración | batería reproducible del HEAD del PR en CI sin costos adicionales autorizados, contrato API real y rollback | **PENDIENTE** |
| Decisión | aprobación explícita de DEC-003 para cambios productivos y merge específico; revisión de riesgos y costos | **PENDIENTE** |

## Alcance y restricciones

- `PR #3` permanece Draft; `main` sin merge ni cron habilitado.
- El gate actual devuelve `eligible_for_write=False` incluso con 18/18 cotizaciones sintéticas.
- El SQL `sql/DEC003_LAB_NO_PRODUCCION.sql` es una propuesta de laboratorio; no ejecutarlo en Supabase.
- El adaptador HTML de Rava no está homologado contra el sitio actual; la API v5 publicada requiere Bearer token y no concede por sí misma derechos de redistribución.
- La documentación de BYMA sobre APIs especifica contrato de Market Data y acceso para personas jurídicas; un enlace público no habilita redistribuir esos precios.

**Dictamen:** no se puede cerrar EC-007.3 de manera operativa ni declarar actualizaciones verificadas del sitio hasta cumplir los gates bloqueados. Puede cerrarse únicamente una *fase de preparación offline*, si el usuario decide formalizarla separadamente. No modificar los estados de EC-007/DEC-003 por este documento.