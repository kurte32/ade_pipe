# Glossary · Spanish domain terms and their identifiers

Date: 11 October 2026 · Branch `ux-redesign` · **Audience:** everyone · **When to read:** whenever a term in the UI, the TDD or the code is unclear · **Source of truth:** the catalogs served by `GET /api/v1/catalogos` and `backend/app/models.py`.

The business documents (TDD, Propuesta) and the user interface are in Spanish; code, API and
infrastructure are in English with the domain nouns kept verbatim. This table maps each term to
where it lives in the system so support, developers and analysts talk about the same thing.

## Pipeline and sites

| Term (UI / business) | Meaning | In code and data |
|---|---|---|
| Sitio | A candidate store location | table `sitio`, model `Sitio`, `sitio_id`, API `/api/v1/sitios` |
| Número (`#`) | The site's identifier in the load file; stable across loads | `sitio.origen_id` (unique), load column `#`, upsert key |
| Nombre | Site name, usually a street address | `sitio.nombre`, load column `SITIO` |
| Región | Operating region (today Xalapa, Azcapotzalco) | `sitio.region`, load column `REGIÓN` |
| Usuario / código | Three-letter coordinator code from the load file | `sitio.usuario_codigo`, load column `USUARIO`, `coordinador_equivalencia.usuario_codigo` |
| Coordinador | Field user who works the site; sees only their own sites | Entra app role `Coordinador`, group `PIPELINE-Coordinadores`, `sitio.coordinador_oid`, RLS predicate `rls.fn_coordinador_predicate` |
| Administrador | Back-office user who loads, reviews, returns and reassigns | Entra app role `Admin`, group `PIPELINE-Admins`, `/api/v1/admin/*` |
| Sistema | Server-side actor used by background jobs and audited as such | DB session context `rol = Sistema` (not an Entra role) |
| Potencial | Commercial potential from the load file: `Muy alto`, `Alto`, `Medio`, `Bajo`, `Sin estatus` | `sitio.potencial`; the UI shows `Sin estatus` as "Sin definir" |
| Campos | Count of filled columns in the load file (`13/24`) | `sitio.campos_capturados`, `sitio.campos_total`, load column `CAMPOS` |
| Coordenadas / GPS | Latitude and longitude parsed from `COORDENADAS`; `GPS` is kept as text (meaning pending, TDD pendiente 2) | `sitio.lat`, `sitio.lon`, `sitio.gps_texto` |
| Fecha de origen | Date in the load file | `sitio.fecha_origen_utc`, `sitio.fecha_origen_texto` |
| Vigente | The site is still part of the pipeline (not superseded by a later load) | `sitio.vigente`; admin filter "Incluir no vigentes" |
| Estatus / etapa | Stage of the pipeline | catalog table `estatus` (`codigo`, `nombre`, `orden`, `terminal`), `sitio.estatus` |
| Sitio Prospectado | Stage 1: identified, owner unknown | `sitio_prospectado` |
| Dueño Localizado | Stage 2: owner contact captured | `dueno_localizado` |
| Primera visita | Stage 3: visited and measured | `primera_visita` |
| Recepción de documentos | Stage 4: the four PDFs received; end of the coordinator's work | `recepcion_documentos` |
| Descartado | Terminal: left the pipeline (proposed by the coordinator, confirmed by the admin, or direct by the admin) | `descartado` (orden 90, terminal) |
| Entregado | Terminal: handed over to the next business stage | `entregado` (orden 91, terminal) |
| Avanzar / avance | Move a site to the next stage | module `transiciones`, `POST /api/v1/sitios/{id}/transiciones`, history `tipo = avance` |
| Devolver / devolución / devuelto | Admin returns a site to an earlier stage with a reason; the coordinator is notified | `POST /api/v1/admin/sitios/{id}/devolver`, `sitio.devuelto`, `devolucion_motivo`, `devolucion_comentario`, history `tipo = devolucion` |
| Motivo (de devolución) | Reason from the catalog | table `motivo_devolucion` (`calidad_datos`, `contacto_invalido`, `medidas_inconsistentes`, `documento_ilegible`, `documento_incompleto`, `otro`) |
| Reasignar / reasignación | Admin moves a site to another coordinator; the previous phone drops it at the next sync | `POST /api/v1/admin/sitios/{id}/reasignar`, history `tipo = reasignacion`, delta `removed_ids` |
| En revisión del administrador | A load assigned an already-advanced site to another coordinator; the admin must decide | `sitio.en_revision_admin`, `sitio.revision_detalle` |
| Historial | Append-only stage history of a site | ledger table `sitio_estatus_historial` (`tipo`, `origen`, `estatus_anterior`, `estatus_nuevo`, `motivo`, `comentario`) |
| Faltantes | What is missing to advance (returned with a 422) | `faltantes` in the Problem Details body; the PWA mirrors the rule in `precheck`/`requisitos` |

## Captures

| Term | Meaning | In code and data |
|---|---|---|
| Contacto del dueño | Owner's name, phone, optional email and notes (personal data) | `sitio_contacto`, `PUT /api/v1/sitios/{id}/contacto`; excluded from Fabric mirroring |
| Medidas / visita | Front, depth, area (m²), visit date, notes | `sitio_visita` (`frente_m`, `fondo_m`, `area_m2`, `fecha_visita_utc`), `PUT …/visita` |
| Foto | Photo of the property, compressed on the phone, queued offline | `sitio_archivo.tipo = foto` |
| Documento / PDF | One of the four required PDFs, uploaded only with signal | `sitio_archivo.tipo = documento`, `tipo_documento` from `catalogo_tipo_documento` (`escritura_hipoteca`, `uso_de_suelo`, `identificacion_propietario`, `predial`) |
| Versión (de archivo) | A replaced document keeps its earlier versions | `sitio_archivo.version`, `vigente` |
| Subida (reanudable) | Chunked, resumable upload session | `subida_sesion` (`abierta`, `escaneando`, `rechazada`, `expirada`), `/api/v1/subidas` |
| Escaneando | Upload received, waiting for the malware scan result | `subida_sesion.estado = escaneando`, job `promote` |
| Publicado / purgado | Document available / deleted by retention (metadata kept) | `sitio_archivo.estado`, `purga_utc`, `purgado_utc`, job `purge` |

## Loads

| Term | Meaning | In code and data |
|---|---|---|
| Carga | A bulk load of sites from CSV, XLSX or XLS | module `cargas`, `/api/v1/admin/cargas` |
| Lote | One uploaded file and its preview | `carga_lote` (`vista_previa`, `confirmado`, `cancelado`), `lote_id` |
| Vista previa | The parsed rows with results, before anything is inserted | `carga_lote.estado = vista_previa`, `carga_fila_staging` |
| Fila | One row of the file | `carga_fila_staging.num_fila` |
| Resultado | Row validation outcome | `ok`, `advertencia`, `error` |
| Advertencia | Doubtful row that needs an admin decision | `resultado = advertencia`, `decision_admin` (`aprobar`, `excluir`) |
| Acción prevista | What confirming will do with the row | `accion_prevista`: `insertar` (new site), `actualizar` (existing, captured data untouched), `revision` (goes to admin review) |
| Confirmar | Insert and update sites in one transaction | `POST …/confirmar`, audit `carga_confirmada` |
| Cancelar (carga) | Discard the preview; nothing written | `POST …/cancelar`, audit `carga_cancelada` |
| Huella | SHA-256 of the file, shown truncated | `carga_lote.hash` |

## Identity, sync and platform

| Term | Meaning | In code and data |
|---|---|---|
| Equivalencia | Mapping of a load-file user code to a corporate account | `coordinador_equivalencia` (`usuario_codigo`, `correo`, `oid`, `nombre`, `activo`), resolved through Graph |
| Cuenta resuelta / sin resolver | Whether the email mapped to an Entra object id | `coordinador_equivalencia.oid` null or not |
| oid | Entra object id of a user | `*_oid` columns, token claim `oid` |
| Aviso | In-app notification to the coordinator (today: returns) | `notificacion_outbox`, `/api/v1/notificaciones`, Teams activity feed when published |
| Sincronizar / pendiente de sincronizar | Send the queued captures and pull the latest sites | PWA sync engine; Dexie `operaciones` states `pendiente`, `enviando`, `bloqueada`, `error` |
| Requiere atención / bloqueada | A queued change the server rejected (412 or 422) and the coordinator must resolve | `operaciones.estado = bloqueada`, conflict panel |
| ETag / rowversion | Optimistic concurrency token of a site | `sitio.rowversion` (`version_id_col`), headers `ETag` / `If-Match`, 412 on mismatch |
| Idempotency-Key | Header that makes a retried write return the stored response | `operacion_idempotente`, purged after `IDEMPOTENCY_TTL_DAYS` |
| Correlación / referencia | Id that links a user-visible error to the server log | `X-Correlation-Id` header, Problem Details `instance`, `auditoria.correlation_id` |
| Auditoría / bitácora | Immutable record of every write and download | ledger table `auditoria` (`accion`, `entidad`, `entidad_id`, `rol`, `ip`, `detalle`) |
| RLS | Row-level security: each coordinator sees only their rows at the database | `rls.coordinador_policy`, `SESSION_CONTEXT('oid')`, `SESSION_CONTEXT('rol')` |
| Pendiente (TDD) | A numbered open item of the TDD v0.1 (1 to 13) | `architecture/TO_BE.md` §9–10, `Propuesta_mejoras_TDD_v0.1.md` |
| Negocio, TI, Seguridad, Legal, Identidad, Datos, Mercadotecnia, Subdirección de IA | Organisational owners used in risk and decision tables | `architecture/RISK_REGISTER.md`, `docs/IMPROVEMENT_BACKLOG.md` |
