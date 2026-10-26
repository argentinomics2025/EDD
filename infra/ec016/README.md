# EC-016 Plan B — servicios de GitHub Actions

**NO APTO PARA PRODUCCIÓN. NO EJECUTADO EN ESTA INTERVENCIÓN.**

Procedimiento vigente: [ec-016-plan-b.md](../../docs/ec-016-plan-b.md).
Dos jobs: escaneo nativo obligatorio con action oficial fijada; luego PostgreSQL
service container, bootstrap sintético, PostgREST y las once pruebas originales.
Sin Compose, sin imagen Trivy exportada ni descarga manual de DB en contenedor.

La plantilla en esta rama debe ser autorizada y copiada a main para activar Plan B;
no se hizo ese cambio ni se configuró EC016_APPROVED_SHA. El CLI anterior devuelve
PLAN_B_WORKFLOW_REQUIRED. Los archivos de Plan A se conservan como antecedente y
para regresiones; ningún workflow nuevo los usa para orquestar el laboratorio.

Validación local sin Docker, red ni SQL:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m infra.ec016.check_local
```

No utilizar el daemon de Codex. No ejecutar compose.yaml ni legacy_main.
