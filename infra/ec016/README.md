# EC-016 — laboratorio GitHub-hosted, listo para autorización

**PAQUETE EXPERIMENTAL. NO REGISTRADO EN MAIN. NO AUTORIZADO PARA EJECUCIÓN. NO APTO PARA PRODUCCIÓN.**

Procedimiento vigente y comandos: [ec-016-runbook.md](../../docs/ec-016-runbook.md).
El workflow estable se registra exclusivamente en main tras aprobación; selecciona
un SHA experimental mediante variable externa y confirmación manual unipersonal.
No requiere segundo revisor ni presume protecciones no verificadas. No se utiliza
el daemon de Codex: engine-approval.json permanece bloqueado.

No ejecutar compose.yaml directamente: es deliberadamente vacío. github_runner
orquesta únicamente el job autorizado ubuntu-24.04; labctl conserva preflight,
atestación y limpieza propia. security_gate exige revisión de imágenes antes de SQL.
Las once integraciones no se han ejecutado. Ver locks/security-review.json para
evidencia verificable y límites, y el runbook para política de vulnerabilidades.

Pruebas preparatorias sin servicios:

```bash
python -m unittest discover -s tests -p 'test_ec016*.py' -v
```

Los documentos previos son antecedentes, no instrucciones alternativas de arranque.
