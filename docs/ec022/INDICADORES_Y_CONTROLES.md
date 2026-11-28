# EC-022.0 / EC-022.1 — Inventario y controles
Fecha: 2026-11-27. Alcance: solo lectores; no escritura ni publicación.
## Reutilización
- BCRA: bcra_data e historial_bcra, id 31 UVA, 259 observaciones 2026-03-02 a 2026-11-27, sin duplicados. No ampliar el allowlist del escritor EC-021.
- IPC: datos_inflacion, 130 registros; último octubre 2026 2.2%. Auditar continuidad y significado de value antes de acumulaciones.
- RIPTE: datos_salarios, 57 meses únicos enero 2022–septiembre 2026; último 2.0%. Solo variación, no nivel.
## Nuevas series
- CER y UVA histórico: BCRA API v4; validar identidad y cobertura diaria.
- RIPTE nominal: página oficial Seguridad Social, cotejar variación publicada.
- CVS e índice salarial: INDEC, archivos originales, verificar base/unidad/edición y estructura; descarga no equivale a parser validado.
- Tasas y volumen hipotecario: BCRA estadísticas de préstamos y tasas, verificar definiciones, moneda, período, flujo vs saldo.
- Ofertas: BCRA Transparencia y bancos, 7 candidatos, siguiente EC-022.3; no ranking incompleto.
## Persistencia propuesta
Una tabla de observaciones nuevas con clave (serie, periodo, edición), valor numeric, unidad, URL, hash SHA256, fecha de recuperación, aprobación explícita. Mantener originales y revisiones; publicar solo edición aprobada, nunca usar max(fecha de carga) como sustituto de aprobación. Rol exclusivo INSERT/SELECT acotado, RLS, no UPDATE/DELETE; credenciales solo después de pruebas aisladas. No duplicar series existentes sin justificar cobertura. Ninguna migración aplicada.
## Próximos criterios verificables
1. Ejecutar pruebas contra los archivos exactos de esta rama.
2. Probe real BCRA/INDEC/RIPTE, sin credenciales ni DML. Confirmar formato y cobertura.
3. Completar parsers CVS, salarios, tasas y volumen; contrastar cifras oficiales.
4. Ensayar almacenamiento y rollback aislados, permisos y idempotencia.
5. Verificar frontend y registrar ARGUS. DEC-003/006/008 vigentes.
No certificar costo incremental de Actions sin verificar cupo/presupuesto. EC-022.1 no cerrada.
