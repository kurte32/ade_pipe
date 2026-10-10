# Propuesta de mejoras al diseño · Pipeline de Posibles Tiendas

Revisión de `TDD_Pipeline_Tiendas_v0.1.pdf` y `Guia_Integracion_Entra_ID_React_FastAPI.pdf`.
Fecha: 10 de octubre de 2026. Insumo para la versión 0.2 del TDD.

## 1. Qué se busca construir

Una plataforma para que diez coordinadores regionales (hoy en Xalapa y Azcapotzalco) lleven desde un Android administrado el pipeline de inmuebles candidatos a tienda. Cada coordinador ve solo sus sitios y los avanza por cuatro estatus (Sitio Prospectado → Dueño Localizado → Primera visita → Recepción de documentos), capturando contacto, medidas, fotos y PDF. Un administrador carga los sitios desde CSV o Excel, aprueba filas dudosas y puede devolver un sitio a un estatus anterior con motivo, lo que avisa al coordinador por Teams. Los documentos deben quedar en Fabric, con retención de 5 años, listos para que un agente de IA los inspeccione después. Todo bajo Entra ID, con aislamiento por coordinador en API, servicio y base de datos, y operación offline en campo.

La volumetría actual es pequeña: 87 sitios, 10 usuarios, 2 regiones. Eso importa para las propuestas: donde haya que elegir, se prefiere quitar un salto o un componente antes que agregar uno.

Convenciones de este documento:

- Se cuestionan libremente las decisiones de diseño de la sección 4.3 del TDD. No se reabren las decisiones de negocio de la sección 17.1.
- Los PENDIENTES del TDD se respetan. Donde ayuda, se propone un valor por defecto y se nombra al responsable, pero la marca se mantiene.
- Lo marcado como **verificar** es una afirmación sobre Azure o Entra que debe confirmarse en Microsoft Learn o en el tenant antes de darla por buena.

## 2. Resumen de prioridades

| # | Propuesta | Secciones del TDD | Impacto |
|---|-----------|-------------------|---------|
| A1 | Definir explícitamente el modelo "abrir sin token, sincronizar con token" y la caché de MSAL | 5.4, 10, guía B3 | Alto: sin esto la PWA no funciona en campo |
| A2 | Documentos definitivos en Blob/ADLS Gen2 con shortcut a OneLake, en vez de escribir en OneLake desde el backend | 4.2, 4.3, 9, 16 | Alto: elimina el riesgo principal de almacenamiento y resuelve retención y escaneo |
| A3 | Los PDF se suben solo con conexión; la cola offline guarda contacto, medidas y fotos comprimidas | 9.2, 10, 16 | Alto: elimina el riesgo número uno del TDD |
| A4 | Corregir la justificación de los dos frontends y fijar hospedaje de los SPA | 4.2, 4.3 | Medio |
| A5 | Especificar la semántica de reenvío offline: orden por sitio, ETag encadenado, idempotencia | 7.2, 10, 12 | Alto: evita conflictos falsos y duplicados |
| B1 | Completar RLS: tablas hijas, bypass de Admin, pooling, y qué se replica a Fabric | 5.2, 5.3, 6 | Alto: hoy la réplica en Fabric contiene datos personales sin control |
| B2 | Bitácora realmente inmutable: permisos INSERT-only o tablas ledger | 6, RF-10 | Medio |
| B3 | Estados terminales y camino negativo en la máquina de estados | 7 | Medio: hoy un sitio no viable no tiene salida |
| B4 | Tablas faltantes: idempotencia, sesión de subida, outbox de notificaciones, catálogo de estatus | 6 | Medio |
| B5 | Resolver oid desde correo vía Graph y pedir el permiso | 6, 8.3, guía 8 | Medio |
| B6 | Notificaciones Teams: opciones reales tras el retiro de connectors | 11 | Medio |
| C1 | Endurecer la validación del token (issuer v2, scp, azp) y Assignment required en el SPA admin | guía A5, A10, C2 | Medio |
| C2 | Un solo dominio para SPA y API detrás de Front Door; sin CORS en producción | guía C3, TDD 4.2 | Bajo-medio |
| C3 | Riesgo conocido de loginRedirect en PWA instalada | guía B7, D | Medio |
| D1 | Fase 0 de spikes antes de cimientos | 15.1 | Alto para el calendario |

## 3. Parte A · Decisiones de arquitectura a revisar

### A1. Offline-first contra la sesión de MSAL

**Hallazgo.** La guía configura `cacheLocation: "sessionStorage"` (B3) y lo deja como nota al pie. El TDD (sección 10) exige que la PWA funcione sin señal. Con sessionStorage, al cerrar la app el coordinador pierde la cuenta activa; sin conexión no puede volver a iniciar sesión, así que no entra a la app aunque tenga los datos en IndexedDB. Además la Parte D de la guía anota que el refresh token de un SPA dura 24 horas: tras un día sin señal, la renovación silenciosa falla.

**Por qué importa.** Es la decisión que define si la PWA sirve en campo. Hoy está repartida entre una nota de la guía y una frase del TDD, y las dos apuntan en direcciones opuestas.

**Propuesta.**

1. Separar dos conceptos en el TDD: *acceso a la app* y *autorización para sincronizar*. La app abre y muestra los datos de IndexedDB del último usuario sin exigir token vigente. El token solo se necesita para sincronizar y para descargar datos nuevos.
2. Usar `localStorage` para MSAL, con la justificación de que el dispositivo está bajo Intune con política de protección de aplicaciones (PIN, cifrado, borrado selectivo). Decisión a cerrar con Seguridad; conviene registrarla en 5.4 como decisión y no como nota.
3. Fijar el navegador: Microsoft Edge para Android. Es el navegador que Intune administra con políticas de protección de aplicaciones (PIN, restricción de copiar y pegar, borrado selectivo) y permite forzar que los enlaces de apps administradas se abran en él. Esto resuelve el pendiente 10 en lo técnico; queda confirmar con el equipo de Intune que el borrado selectivo de Edge limpia también IndexedDB y localStorage del sitio (**verificar**).
4. Documentar el comportamiento esperado tras 24 horas sin conexión: la cola se conserva, la app muestra "requiere iniciar sesión para sincronizar" y al recuperar señal pide login interactivo y reanuda la cola. Esto ya aparece como prueba obligatoria en la guía; debe ser requisito en el TDD (RNF-02).
5. El service worker no puede llamar a MSAL. Por eso la sincronización debe correr en primer plano de la app (al abrir, al evento `online`, y con un temporizador), no con Workbox Background Sync, que reenvía las peticiones originales con el encabezado Authorization ya caducado. La cola vive en Dexie como operaciones de dominio, no como peticiones HTTP crudas. Background Sync queda como disparador opcional que despierta la app, nada más.

### A2. Documentos definitivos en Blob/ADLS Gen2 con shortcut a OneLake

**Hallazgo.** El TDD escribe los archivos definitivos en OneLake desde el backend con el SDK de Data Lake, pasando antes por un Blob de staging. La propia sección 16 marca como riesgo el rendimiento y los permisos de escribir en OneLake desde fuera de Fabric, y la sección 9.2 deja "por validar" la disponibilidad de escaneo antimalware. El pendiente 7 pide retención legal.

**Propuesta.** Invertir la dirección: los archivos definitivos viven en una cuenta de almacenamiento de Azure (ADLS Gen2, con espacio de nombres jerárquico) y Fabric los ve mediante un **shortcut de OneLake** a esa cuenta, dentro de `Files/` del Lakehouse. Para el agente de IA y para Fabric el resultado es el mismo: los archivos aparecen en el Lakehouse en la ruta `Files/pipeline/...`, sin copia.

Lo que se gana:

- **Desaparece el salto doble** (staging → OneLake) y el riesgo de escritura externa a OneLake. El "completar" de una subida es una copia dentro de la misma cuenta o incluso solo un cambio de contenedor.
- **Retención de 5 años aplicada por la plataforma.** Las políticas de inmutabilidad de Blob (retención por tiempo y *legal hold*) impiden borrar o modificar el archivo durante el plazo, incluso al propietario de la cuenta. El proceso de purga del TDD (9.3) se reduce a borrar lo que ya venció. El *legal hold* responde al pendiente 7 sin desarrollo propio. Confirmar soporte de inmutabilidad a nivel versión en cuentas con espacio de nombres jerárquico (**verificar**).
- **Escaneo antimalware nativo.** Microsoft Defender for Storage escanea cada blob al subirse y publica el resultado como etiquetas de índice y como eventos de Event Grid. Matiz importante: las etiquetas de índice no están disponibles en cuentas con espacio de nombres jerárquico. Por eso se propone **dos cuentas**: una cuenta Blob plana para staging (con escaneo y etiquetas) y la cuenta ADLS Gen2 para lo definitivo. El backend lee la etiqueta o escucha el evento antes de promover el archivo.
- **Private endpoints y acceso con identidad administrada** quedan en servicios donde ya están probados. El acceso restringido a OneLake que el TDD marca como "por validar" deja de ser crítico.

Costo: un shortcut requiere una credencial delegada en Fabric (identidad del workspace o service principal) con permiso de lectura sobre la cuenta; si la cuenta está detrás de private endpoint hay que habilitar el acceso de workspace de confianza de Fabric (**verificar** en el tenant). La sección 4.3 debería recoger esta decisión como alternativa evaluada y, de aceptarse, la ruta de archivos y el diagrama cambian.

### A3. Los PDF no se capturan offline

**Hallazgo.** El riesgo número uno del TDD es "archivos de 150 MB capturados sin señal" (16), y la sección 9.2 pide validar las cuotas de IndexedDB para guardar archivos grandes. El requisito RF-08 solo exige que los PDF se suban por partes y de forma reanudable; no exige que se capturen sin conexión.

**Propuesta.** Separar por tipo de dato:

| Dato | Se captura offline | Se sube |
|------|--------------------|---------|
| Contacto, medidas, avance de estatus | Sí | Al sincronizar |
| Fotos | Sí, comprimidas en el cliente, con tope por sitio (propuesta: 10 fotos, 1.5 MB cada una; pendiente 6) | Al sincronizar |
| PDF | No. La app indica "requiere conexión" | Solo en línea, por partes y reanudable |

Un PDF de hipoteca o uso de suelo llega al coordinador por correo o mensajería; rara vez se genera en el momento de la visita sin señal. La subida reanudable (RF-08, HU-11) ya cubre los cortes de conexión durante la subida. Con esto el riesgo de cuotas en el teléfono se reduce a decenas de MB de fotos, y la prueba de concepto de IndexedDB se acota.

Si el negocio confirma que sí hay PDF generados en campo sin señal, la alternativa es permitir un solo PDF en espera por dispositivo, con aviso explícito.

### A4. Dos frontends: la razón declarada y el hospedaje

**Hallazgo.** La sección 4.3 justifica los dos frontends porque "permite políticas de acceso condicional distintas para el administrador", y la guía lo repite (sección 2). El acceso condicional de Entra se evalúa contra el **recurso** al que se pide el token, no contra el cliente público. Los dos SPA piden tokens para el mismo recurso, `pipeline-api`, así que una política dirigida a la API aplica igual a ambos. La política más estricta para administradores se logra dirigiéndola al grupo `PIPELINE-Admins`, no separando SPA. Verificado en la documentación de "Target resources" de acceso condicional.

Además, la sección 4.2 no dice dónde se hospedan los dos SPA. Solo aparece el contenedor de la API.

**Propuesta.**

1. Mantener dos aplicaciones, pero por las razones correctas: UX distinta (móvil offline contra escritorio), paquete pequeño para la PWA, y ciclos de despliegue separados. Corregir el texto de 4.3 y de la guía.
2. Reforzar lo que sí separa a los administradores: *Assignment required = Yes* también en la aplicación empresarial `pipeline-web-admin`, con solo `PIPELINE-Admins` asignado. Así un coordinador no puede ni iniciar sesión en la web de administración. Hoy la guía solo lo pide para la API (A10).
3. Un monorepo (pnpm workspaces o similar) con `apps/pwa-coordinador`, `apps/web-admin` y paquetes compartidos `api-client`, `auth` y `ui`. Es la mitigación que 4.3 ya menciona, hecha concreta.
4. Hospedaje de los SPA: Azure Static Web Apps o un contenedor de Blob con sitio estático, detrás del mismo Front Door que la API (ver C2).

### A5. Semántica del reenvío offline

**Hallazgo.** El TDD exige `If-Match` con rowversion para las transiciones (7.2, 12) y un identificador único por operación para no duplicar (10). Falta cómo se combinan cuando un coordinador, sin señal, captura el contacto y luego avanza el estatus del mismo sitio. Al sincronizar, el `PUT /contacto` cambia el rowversion; la transición que viene detrás trae el rowversion viejo y el servidor la rechaza, aunque no hubo ningún conflicto real.

**Propuesta.** Escribirlo en la sección 10:

- La cola es FIFO **por sitio**. Sitios distintos se sincronizan en paralelo; operaciones del mismo sitio, en orden.
- Cada operación guarda el ETag que conocía al crearse, pero al reenviar la cadena el cliente **encadena** el ETag devuelto por la operación anterior. Solo la primera operación de la cadena compara contra el estado que el coordinador vio.
- Si una operación falla por precondición (412) o por regla de negocio (422), la cadena de ese sitio se detiene y las operaciones restantes quedan marcadas "bloqueadas por conflicto" para revisión del coordinador. Las demás cadenas siguen.
- Distinguir dos encabezados: `Idempotency-Key` (misma operación reenviada, el servidor devuelve la respuesta guardada) e `If-Match` (precondición de concurrencia). Hoy el TDD los mezcla en "idempotente".
- `PUT /contacto` y `PUT /visita` pueden ser *last write wins* sin `If-Match`, porque solo escribe el coordinador dueño. `POST /transiciones` y `POST /admin/devolver` sí exigen `If-Match`.
- Alternativa más simple si el equipo lo prefiere: un `POST /sitios/{id}/sync` que recibe la cadena completa y la aplica en una transacción. Menos peticiones en 4G y conflictos atómicos; a cambio, un contrato menos REST.

Esto requiere la tabla de idempotencia de B4 y un `GET /sitios?desde={rowversion}` para refrescar solo lo cambiado, que también ayuda al objetivo de lista inicial en menos de 3 segundos (RNF-08).

## 4. Parte B · Huecos de diseño

### B1. Row-Level Security completo y lo que se replica a Fabric

Lo que falta en 5.2 y 6:

- **Tablas hijas.** `sitio_contacto`, `sitio_visita` y `sitio_archivo` no tienen `coordinador_oid`. El predicado de RLS necesita un `EXISTS` contra `sitio` o una columna `coordinador_oid` desnormalizada y mantenida por trigger o por la capa de servicio. Propuesta: desnormalizar; es más barato en consultas y más fácil de probar.
- **Bypass de administrador.** El predicado debe ser `coordinador_oid = SESSION_CONTEXT('oid') OR SESSION_CONTEXT('rol') = 'Admin'`. Hoy no se dice cómo el Admin ve todo.
- **Pooling.** Con SQLAlchemy, `SESSION_CONTEXT` se fija en el evento `checkout` y se limpia en `checkin`. No usar `@read_only = 1`, porque impide reasignar la conexión a otro usuario dentro del pool.
- **Reasignación.** Al cambiar `coordinador_oid` (RF-09), el predicado de bloqueo de RLS evita que el coordinador anterior siga viendo el sitio, pero la caché local del teléfono lo conserva hasta la siguiente sincronización. El `GET /sitios?desde=` debe devolver también los sitios que *dejaron* de ser del coordinador, para que la app los borre.
- **Fabric Mirroring no respeta RLS.** El mirroring lee con una identidad de servicio y replica las tablas completas. Eso lleva `sitio_contacto` (datos personales de propietarios) a Fabric, donde el control de acceso es otro. Decisión a registrar en 5.3: excluir `sitio_contacto` y `auditoria` del mirroring (se eligen tablas al configurarlo), o replicarlas y definir roles de acceso a datos de OneLake. Para el agente de IA, los contactos no deberían hacer falta.
- **Private endpoint en SQL y mirroring.** Si Azure SQL queda solo con private endpoint, el mirroring necesita un *virtual network data gateway* o un *on-premises data gateway*. Es un componente más que hoy no está en el diagrama ni en costos. Alternativa: permitir servicios de Azure confiables hacia el servidor SQL, decisión con Seguridad.
- **Container Apps con VNet.** Los private endpoints a SQL, Blob y Key Vault implican un entorno de Container Apps integrado a una red virtual. Conviene decirlo en 4.2 y 13, porque cambia el perfil de carga de trabajo y el costo.

### B2. Bitácora inmutable de verdad

`sitio_estatus_historial` y `auditoria` dicen "solo inserción", pero es una convención de código. Dos refuerzos, de menor a mayor:

1. La cuenta de la aplicación solo tiene `INSERT` y `SELECT` sobre esas tablas. Sin `UPDATE` ni `DELETE`. Se prueba en la suite de seguridad.
2. Declararlas como **tablas ledger de solo anexar** de Azure SQL, que dan evidencia criptográfica de manipulación y cubren RF-10 ante una auditoría externa. Costo bajo a este volumen.

### B3. Estados terminales y camino negativo

La máquina de estados de la sección 7 solo avanza. No hay forma de que un coordinador diga "el dueño no se localizó" o "el local ya se rentó", ni de que el administrador cierre un sitio. Sin embargo, el pendiente 7 ya habla de "cierre o descarte del sitio" para contar la retención.

Propuesta: agregar dos estados terminales, `Descartado` (con motivo de catálogo, lo propone el coordinador y lo confirma el administrador, o directo por el administrador) y `Entregado` o el nombre que use el negocio para "salió del pipeline hacia la siguiente etapa". La columna `vigente` de `sitio` no basta porque no dice por qué dejó de estar vigente. Esto afecta RF-03, la tabla 7.1, el catálogo de motivos (pendiente 8) y el evento de inicio de retención (pendiente 7). Es decisión de negocio; aquí solo se señala el hueco.

Sobre `requisito_transicion` como tabla de reglas ("configuración, no código"): con cuatro transiciones y reglas que requieren consultar otras tablas (documentos vigentes por tipo), un motor de reglas en base de datos cuesta más que lo que ahorra. Propuesta: las reglas viven en código, una función por transición; lo que es configuración son los **parámetros** (campos mínimos de contacto, catálogo de documentos requeridos por estatus, distancia de duplicados). Mantener `catalogo_tipo_documento.requerido_en_estatus`; eliminar `requisito_transicion` o reducirla a parámetros.

### B4. Tablas que faltan en el modelo

| Tabla | Para qué | Campos mínimos |
|-------|----------|----------------|
| `operacion_idempotente` | Reenvíos de la cola offline (A5) | clave, usuario_oid, ruta, hash_cuerpo, codigo_respuesta, cuerpo_respuesta, fecha_utc. Se purga a los 7 días |
| `subida_sesion` | Estado de una subida por partes (9.2) | id, sitio_id, usuario_oid, tipo_documento, bytes_total, tamano_parte, partes_recibidas, sha256_esperado, estado, expira_utc |
| `notificacion_outbox` | Avisos Teams con reintento (11) | id, sitio_id, destinatario_oid, tipo, cuerpo, intentos, estado, siguiente_intento_utc, enviada_utc |
| `estatus` | Catálogo con orden y si es terminal (B3) | codigo, nombre, orden, terminal |
| `motivo_devolucion` | Catálogo de calidad (pendiente 8) | codigo, nombre, activo |

Y dos columnas: `sitio.estatus_anterior_devolucion` o equivalente para pintar "devuelto por calidad" sin recorrer el historial, y `coordinador_oid` en las tablas hijas (B1).

### B5. De correo a oid con Microsoft Graph

La regla 8.3 marca como error una "equivalencia que no resuelve a una cuenta de Entra" y la tabla `coordinador_equivalencia` guarda `oid`. Nadie dice cómo se obtiene el oid a partir del correo. Opciones: que el administrador lo pegue a mano (frágil) o que el backend lo resuelva con Graph (`GET /users/{correo}`) al guardar la equivalencia y lo revalide en cada carga.

Propuesta: resolver con Graph usando la identidad administrada del backend con el permiso de aplicación `User.ReadBasic.All`. Agregarlo al mensaje para el equipo de identidad (guía, sección 8), que hoy solo pide Graph "más adelante" para Teams. Guardar siempre el oid y usar el correo solo para buscar: el UPN puede cambiar, el oid no.

### B6. Notificaciones en Teams tras el retiro de connectors

Los *Office 365 connectors* y sus webhooks entrantes están en retiro (anunciado en agosto de 2024, apagados desde mayo de 2026), y además apuntaban a canales, no a personas. Las opciones vigentes para avisar a un coordinador concreto:

| Opción | Cómo | Pros | Contras |
|--------|------|------|---------|
| Notificaciones de actividad de Teams vía Graph | App de Teams (manifiesto) instalada a los usuarios, permiso `TeamsActivity.Send`, el backend llama a Graph con identidad administrada | Recomendada por Microsoft, llega al feed de actividad, enlaza a la PWA | Requiere publicar una app de Teams en el tenant y permiso de administrador |
| Power Automate (Workflows) | El backend publica el evento (HTTP o Service Bus) y un flujo envía mensaje al chat del usuario | Menor desarrollo, TI suele tener el servicio | El flujo corre con la identidad de su dueño; límites de licencia; mensaje con identidad "Flow bot" |
| Bot de Teams | Azure Bot Service con mensajes proactivos | Máxima flexibilidad | El más costoso de operar para un solo tipo de aviso |

Propuesta: la fase 2 entrega el aviso **dentro de la PWA** (ya es respaldo en 16) sobre la tabla `notificacion_outbox`; la fase 3 conecta la primera opción si identidad aprueba la app de Teams, o la segunda si no. Así la notificación nunca bloquea el flujo, como pide 11.

## 5. Parte C · Correcciones y endurecimiento de la guía de Entra

### C1. Validación del token

- **Issuer.** Una vez hecho A5 (`requestedAccessTokenVersion = 2`), dejar un solo issuer válido. Aceptar v1 y v2 a la vez sirve para arrancar, no para producción.
- **Tokens de aplicación.** `require_role` acepta cualquier token con `roles`. Si algún día se definen permisos de aplicación en `pipeline-api`, un token de cliente confidencial (sin usuario) también traería `roles`. Exigir la claim `scp` con `access_as_user` y rechazar tokens sin `oid` de usuario.
- **Clientes autorizados.** Opcional: validar `azp` contra los dos Client ID de los SPA. Defensa en profundidad para que un token pedido por otra aplicación del tenant hacia la API no sea aceptado. Alternativa de configuración: *Authorized client applications* en "Expose an API".
- **tid.** Comparar `tid` con el tenant esperado, además del issuer.
- **Assignment required en los SPA.** Ver A4.2.
- **Licencia.** La asignación de roles a grupos requiere Entra ID P1; la guía ya lo advierte. Si no hay P1, la alternativa es asignar usuarios directamente a los roles, que a 10 usuarios es manejable, y documentar quién lo mantiene.

### C2. Un dominio, sin CORS en producción

La guía solo lista orígenes `localhost` en C3. En producción, los dos SPA y la API serían tres orígenes distintos. Propuesta: publicar todo bajo un solo host de Front Door con enrutamiento por ruta: `/` para la PWA, `/admin/` para la web de administración (o un segundo host) y `/api/*` hacia Container Apps. Ventajas: sin CORS, una sola política de CSP, un solo certificado, y el WAF cubre también los estáticos. Los Redirect URI de producción en Entra se definen con esos hosts.

### C3. loginRedirect dentro de la PWA instalada

Es un problema reportado de MSAL en PWA instaladas en Android (**verificar** en dispositivo): el redirect sale a Edge o Chrome y, al regresar, puede aterrizar en una pestaña del navegador y no en la ventana de la app instalada, perdiendo el estado. La guía lo lista como prueba en el teléfono; conviene subirlo a riesgo en la sección 16 y probarlo en la Fase 0 (D1). Mitigaciones si falla: usar la PWA desde Edge sin instalar (Edge administrado por Intune lo permite), o `display: "minimal-ui"` en el manifiesto. También: excluir las rutas de respuesta de Entra del *navigation fallback* del service worker, para que la respuesta con `#code=` no sea servida desde caché.

### C4. Menores en la guía

- B5: `acquireTokenRedirect` dentro de un `catch` sin revisar `inProgress` es justo el bucle que la nota B7 advierte. Mover la lógica a un hook que compruebe `InteractionStatus.None`.
- La guía no cubre cierre de sesión en dispositivo compartido ni `prompt: "select_account"`. Agregar un párrafo si hay teléfonos compartidos entre coordinadores (preguntar a negocio).
- `PyJWKClient(cache_keys=True)`: fijar también `lifespan` y manejar el reintento cuando llega un `kid` desconocido por rotación de llaves.

## 6. Parte D · Roadmap y pruebas

### D1. Fase 0: spikes que desbloquean el diseño

Las tres incógnitas que pueden cambiar la arquitectura están hoy repartidas en fases 1 a 3. Propuesta: una Fase 0 de dos a tres semanas, antes de Cimientos, con tres pruebas de concepto y criterio de salida escrito:

1. **Login y offline en un Android real con Intune y Edge.** Inicio de sesión con redirect en PWA instalada y sin instalar; renovación tras 24 horas sin señal; borrado selectivo y qué limpia. Decide A1 y C3. Responsables: equipo de Intune e identidad, con el frente.
2. **Almacenamiento.** Subir un PDF de 150 MB por partes a Blob staging, escaneo con Defender, promoción a ADLS Gen2 con inmutabilidad, y verlo desde un shortcut en el Lakehouse. Decide A2 y la ruta de archivos.
3. **RLS y mirroring.** Esquema mínimo con RLS, predicado de Admin, prueba de acceso cruzado, mirroring con selección de tablas y, si aplica, gateway de red virtual. Decide B1.

Con los resultados, se publica el TDD 0.2 y arranca la Fase 1.

### D2. Ajustes a la estrategia de pruebas (14)

- Agregar prueba de contrato de RLS con dos oid y un Admin, ejecutada en CI contra una base real, como ya pide la sección 14, pero también sobre las tablas hijas.
- Agregar pruebas de la cadena offline (A5) con Playwright y emulación de red: contacto más transición sin señal, devolución del administrador a mitad de la cadena, reenvío duplicado.
- Agregar prueba de permisos negativos sobre `auditoria` e historial (B2).
- Fijar `America/Mexico_City` como zona en pruebas de fechas; México ya no aplica horario de verano, pero la zona IANA evita depender de un offset fijo.

### D3. Otros menores del TDD

- 8.1: la neutralización de fórmulas aplica a exportaciones y a la vista previa. Hoy no hay exportación en alcance; dejar la regla para cuando la haya y aplicarla a la bitácora descargable de HU-15.
- 8.1: leer Excel "todo como texto" con pandas convierte celdas de fecha a cadenas con formato interno. Leer con openpyxl respetando el tipo de celda y normalizar después, o documentar el formato exacto que produce pandas.
- 8.4: definir qué pasa con filas cuyo `#` ya existe pero con `REGIÓN` o `SITIO` distintos. Propuesta por defecto: advertencia que requiere decisión, igual que el cambio de usuario.
- 12: `GET /archivos/{id}` para un PDF de 150 MB a través de Front Door y Container Apps debe soportar `Range` y conviene comprobar los tiempos de espera de ambos servicios para respuestas largas (**verificar**). Si resulta problemático, la alternativa es un SAS de delegación de usuario de minutos, emitido por el backend, solo para la web de administración.
- 13: agregar al pipeline de CI el escaneo del paquete web (dependencias npm) además del contenedor.
- 6: `sitio.fecha_origen_utc` proviene de la columna FECHA, que el TDD interpreta como hora de Ciudad de México. Guardar también el valor original como texto para auditoría de la carga.

## 7. Qué cambia en el TDD 0.2 si se aceptan estas propuestas

- Sección 4.2 y figura 1: hospedaje de SPA, dos cuentas de almacenamiento, shortcut en vez de escritura a OneLake, gateway de red virtual si aplica.
- Sección 4.3: nueva justificación de los dos frontends; decisión Blob/ADLS Gen2 más shortcut; decisión de caché MSAL y navegador Edge.
- Sección 5: RLS completo, tablas excluidas del mirroring, bitácora ledger, Assignment required en SPA admin.
- Sección 6: tablas de B4 y columnas desnormalizadas.
- Sección 7: estados terminales; reglas en código, parámetros en configuración.
- Sección 9 y 10: PDF solo en línea; semántica de cola por sitio y ETag encadenado.
- Sección 11: opciones de Teams vigentes.
- Sección 15.1: Fase 0.
- Sección 16: riesgo de loginRedirect en PWA instalada; se retira o reduce el riesgo de archivos de 150 MB offline.
- Sección 17.2: nuevos pendientes: estados terminales (negocio), tablas a replicar a Fabric (seguridad y datos), app de Teams o Power Automate (TI), teléfonos compartidos (negocio).

## Fuentes consultadas para las afirmaciones marcadas como verificadas

- Acceso condicional, recursos de destino: https://learn.microsoft.com/entra/identity/conditional-access/concept-conditional-access-cloud-apps
- Shortcuts de OneLake a ADLS Gen2: https://learn.microsoft.com/fabric/onelake/create-adls-shortcut y https://learn.microsoft.com/fabric/onelake/onelake-shortcuts
- Mirroring de Azure SQL Database y gateway de red virtual: https://learn.microsoft.com/fabric/mirroring/azure-sql-database
- Edge para Android con políticas de protección de Intune: https://learn.microsoft.com/intune/intune-service/apps/mamedge-overview
- Defender for Storage, escaneo al subir y etiquetas de índice: https://learn.microsoft.com/azure/defender-for-cloud/on-upload-malware-scanning
- Retiro de Office 365 connectors en Teams: https://devblogs.microsoft.com/microsoft365dev/retirement-of-office-365-connectors-within-microsoft-teams/
