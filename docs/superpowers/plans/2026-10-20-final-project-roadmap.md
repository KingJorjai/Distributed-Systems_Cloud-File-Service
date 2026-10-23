# Plan del proyecto final — Cloud File Service

> **Para agentes:** este es un plan de programa (roadmap con milestones), no un plan de implementación tarea a tarea. Antes de ejecutar un milestone, escribir su plan detallado con `superpowers:writing-plans` y ejecutarlo con `superpowers:subagent-driven-development` o `superpowers:executing-plans`.

**Objetivo:** completar el proyecto de Distributed Systems: servicio de ficheros en la nube con cliente transparente, servidor replicado tolerante a fallos y notificación de cambios entre clientes, más memoria, presentación y demostración.

**Arquitectura:** replicación pasiva con un primario y dos secundarios (3 procesos en localhost). El primario ordena y difunde cada mutación con *reliable broadcast* síncrono; los secundarios la aplican en orden y confirman. Los clientes mantienen un estado local `(path, rev, hash)` y reciben notificaciones `UPDT` del primario para descargar o borrar cambios remotos. Un detector de fallos por heartbeats y una elección determinista promueven un secundario cuando el primario cae.

**Stack:** Python 3.10+, `unittest`, `watchdog`, sockets TCP, SQLite (`sqlite3` de la biblioteca estándar), Docker/Compose, MkDocs y PyInstaller (ya existentes).

---

## 1. Contexto y estado actual

### 1.1 Repositorio

- Ruta: `/home/jorjai/Documents/DS/Distributed-Systems_Cloud-File-Service`
- Rama: `main`, último commit `751feb8` (2026-10-07).
- Sin cambios de código pendientes; `AGENTS.md` y `docs/ref/` están sin seguimiento.

### 1.2 Baseline verificado (2026-10-20)

| Comprobación | Resultado |
| --- | --- |
| `python -m unittest discover -s tests -v` | 11 tests OK |
| `python -m ruff check .` | OK |
| `mkdocs build --strict` | OK |

### 1.3 Lo que ya está implementado

- Servidor TCP multihilo con autenticación (`anonimous`, `sar`, `sza`), almacenamiento por usuario y `safe_path`.
- Subida atómica con fichero temporal, límite `MAX_FILE_SIZE` y margen de espacio.
- Cliente `watchdog` recursivo con debounce, cola en memoria, reintento y reconexión.
- Sincronización **unidireccional** cliente → servidor; renombrados como borrado + subida.
- Docker, bundles de release, documentación MkDocs y PDF.

### 1.4 Huecos frente al estado final del proyecto

| Requisito del proyecto | Estado actual |
| --- | --- |
| Fase 1: cliente transparente | Parcial: sube cambios, pero no reconcilia el estado del servidor al arrancar. |
| Fase 2: servidor replicado tolerante a fallos | No existe. Un solo proceso, sin réplicas, sin broadcast, sin elección. |
| Fase 3: ficheros compartidos entre clientes | No existe. Sin notificaciones servidor → cliente ni resolución de conflictos. |
| Revisiones, hashes y conflictos | Solo comentarios en `TODO.md` y en el código. |
| Pruebas de protocolo, servidor y sincronización | Solo hay tests de configuración (`tests/test_config.py`). |
| Memoria, presentación y demo | Hay borradores de actividades, pero no la memoria final del proyecto. |

### 1.5 Material de referencia copiado

- `docs/ref/Course notes-20261020/html/` — 51 ficheros (3,9 MB): `Guide.html`, `P01`–`P04`, `Project.html`, PDFs de temas y recursos.
- `docs/ref/Course notes-20261020/*.pdf`, `docs/ref/guia_docente_DS_2026_27_eng.pdf`, `docs/ref/bibliography.pdf`.
- `docs/ref/Other documents-20261020/` — artículos, informes A1.2 de ejemplo y tests de evaluación.
- `docs/ref/` ocupa 41 MB y no está versionado. Decisión de M0: mantenerlo local y añadirlo a `.gitignore`, salvo que el grupo necesite compartirlo; en ese caso usar Git LFS.

### 1.6 Requisitos extraídos de la documentación del curso

- Tres incrementos: (1) cliente-servidor no fiable, (2) servidor replicado con replicación pasiva, broadcast fiable, detección de fallo del primario y elección, (3) varios clientes comparten ficheros y el servidor les notifica cambios.
- Prueba de concepto: 3 servidores (primario y dos secundarios), 2 clientes, todo en una máquina, configuración manual permitida.
- Memoria con: problema y objetivos, enfoque y arquitectura modular, decisiones con referencias al código, pruebas y resultados, conclusiones y trabajo pendiente.
- Presentación oral de 15 minutos + 5 de preguntas, con una parte por miembro, antes de la entrega final de la memoria.
- Se valora explícitamente lo que queda sin hacer; no se espera un producto comercial.

---

## 2. Estado final (Definition of Done)

### 2.1 Funcional

1. **Cliente transparente:** al arrancar, el cliente concilia su carpeta con el manifiesto del servidor; sube solo lo nuevo o modificado y descarga lo que falte.
2. **Ficheros compartidos:** dos clientes del mismo usuario convergen; un cambio confirmado en uno se refleja en el otro en menos de 2 s; los borrados también se propagan.
3. **Conflictos:** si dos clientes modifican el mismo fichero desde la misma revisión, el servidor conserva una copia oficial y una copia de conflicto con nombre determinista; ambos clientes reciben la copia de conflicto.
4. **Réplica pasiva:** el primario ordena las mutaciones, las difunde y espera confirmación de una mayoría (2 de 3) antes de responder al cliente. Los secundarios aplican en el mismo orden.
5. **Tolerancia a fallos:** si el primario cae, en menos de 5 s otro servidor es elegido; las operaciones confirmadas no se pierden; los clientes se reconectan y siguen operando.
6. **Reincorporación:** un servidor que vuelve se sincroniza desde el primario o desde un secundario actualizado antes de aceptar tráfico.

### 2.2 Calidad y entrega

- Todos los tests pasan, incluida la matriz de aceptación de la sección 6.
- `ruff check .` y `mkdocs build --strict` pasan.
- Documentación actualizada: arquitectura, protocolo, configuración, limitaciones y guía de demo.
- Memoria final en PDF con la estructura exigida y referencias al código.
- Presentación de 15 minutos ensayada y demo reproducible con un comando.
- Tag de release con bundles de cliente y servidor.

### 2.3 Fuera de alcance (se documentará como trabajo pendiente)

- Replicación activa, *virtual synchrony* completa y consenso tipo Raft/Paxos.
- TLS, gestión real de usuarios/permisos y secretos.
- Sincronización por deltas, compresión, *chunking* o ficheros mayores de 10 MB.
- Interfaz gráfica, web o multiusuario entre cuentas distintas.
- Historial de versiones y recolección de basura de lápidas (*tombstones*).

---

## 3. Arquitectura objetivo

### 3.1 Componentes

| Fichero | Responsabilidad |
| --- | --- |
| `szasar.py` | Constantes y framing del protocolo de cliente; límite de longitud de línea. |
| `file_store.py` | Estado del servidor: sistema de ficheros + metadatos SQLite + manifiesto + conflictos. |
| `replication.py` | `ReliableBroadcast` (R-broadcast/R-deliver), log de operaciones y aplicación ordenada. |
| `election.py` | Heartbeats, detector de fallos, términos, elección y *fencing* del primario. |
| `notification_hub.py` | Registro de suscripciones por usuario y envío de `UPDT` a clientes. |
| `server_runtime.py` | Factoría `create_server(config)`, aceptación de conexiones y arranque de réplicas. |
| `serv_fich_multithread.py` | Entrada del servidor; delega en `server_runtime`. |
| `client_state.py` | Estado local SQLite `(path, rev, hash, size, deleted)` y reconciliación. |
| `remote_watcher.py` | Conexión de notificaciones y aplicación de cambios remotos. |
| `sync_client.py` | Watcher local, cola, subida/borrado y coordinación con `client_state`/`remote_watcher`. |
| `cli_fich.py` | Login, arranque/parada ordenada y reconexión. |
| `config.py` | Puertos, rutas, rol, id, peers, timeouts y límites. |
| `docs/protocol.md` | Protocolo cliente-servidor y servidor-servidor. |
| `docs/architecture.md` | Diagramas y flujo de una mutación y de un failover. |
| `docs/limitations.md` | Alcance y trabajo pendiente explícito. |

Se mantiene la estructura plana actual para no romper imports ni el pipeline de release. Cada módulo tiene una única responsabilidad y se prueba de forma aislada.

### 3.2 Modelo de datos

Metadatos por usuario, replicados en cada servidor:

```sql
CREATE TABLE files (
    user      TEXT    NOT NULL,
    path      TEXT    NOT NULL,
    rev       INTEGER NOT NULL,
    hash      TEXT    NOT NULL,
    size      INTEGER NOT NULL,
    mtime_ns  INTEGER NOT NULL,
    deleted   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user, path)
);
```

- `rev` empieza en 1 y se incrementa en cada mutación confirmada de ese path.
- Un borrado deja `deleted = 1` (lápida) para que clientes desconectados lo propaguen al reconciliar.
- El cliente guarda la misma tabla en `client_state.sqlite`, bajo `~/.local/state/cloudfs/<hash>.sqlite`; el hash se deriva de la ruta absoluta de la carpeta local.

### 3.3 Protocolo

Cliente → servidor (ASCII, CRLF, prefijos de 4 caracteres):

| Comando | Respuesta | Uso |
| --- | --- | --- |
| `SYNC` | `OK<count>` + líneas `path\trev\thash\tsize\tdeleted` + `END` | Manifiesto para reconciliación. |
| `STATpath` | `OK<rev>\t<hash>\t<size>` o `ER5` | Estado de un path. |
| `UPLOpath?size?rev?hash` | `OK` o `ER<code>` | Subida con revisión base opcional. |
| `SUBScid` | `OK` | Conexión de control suscrita a cambios. |
| `UPDTpath\trev\thash\tsize\top` | — | Notificación servidor → cliente (`op` = `U`, `D`, `M`). |
| `PING` | `OK` | Keepalive de la conexión de control. |

Compatibilidad: `UPLOpath?size` sigue funcionando; si faltan `rev`/`hash`, el servidor trata la subida como basada en la revisión actual (comportamiento de la fase 1).

Servidor ↔ servidor (una línea JSON por mensaje, CRLF):

| Mensaje | Campos | Uso |
| --- | --- | --- |
| `HELLO` | `id`, `role`, `term`, `last_seq` | Presentación al conectar. |
| `HB` | `id`, `term`, `last_seq` | Heartbeat del primario. |
| `RB` | `term`, `seq`, `op_id`, `user`, `path`, `rev`, `hash`, `size`, `op`, `data_b64` | R-broadcast de una mutación. |
| `ACK` | `term`, `seq`, `id` | Confirmación de R-deliver. |
| `VOTE` | `term`, `candidate`, `last_seq` | Elección. |
| `COORD` | `term`, `leader` | Anuncio de nuevo primario. |
| `SNAP` | `term`, `seq`, `user`, `entries` | Transferencia de estado para reincorporación. |

- `op_id` es `(term, seq)` y hace idempotente la aplicación.
- El payload de datos viaja en base64 dentro de `RB` para mantener el framing por líneas; el límite es `MAX_FILE_SIZE` (10 MB).
- Cada conexión tiene un límite de línea de 8 KiB para comandos; las líneas `RB`/`SNAP` usan un límite separado de 16 MiB.

### 3.4 Flujo de una mutación

1. El cliente envía `UPLO` con `rev` base y hash.
2. El primario valida autenticación, permisos, tamaño y espacio.
3. Si `rev` base no coincide, crea una copia de conflicto y continúa con la copia oficial.
4. El primario asigna `seq`, persiste la intención en su log y hace R-broadcast.
5. Cada secundario aplica la operación, persiste `seq` y responde `ACK`.
6. Con mayoría de `ACK`, el primario confirma localmente y responde `OK` al cliente.
7. El `notification_hub` envía `UPDT` a los demás clientes suscritos del usuario.
8. El cliente receptor consulta `STAT`/`SYNC` si necesita datos y descarga o borra.

La linealizabilidad se apoya en: orden total del primario + aplicación en orden en todas las réplicas + atomicidad del R-broadcast síncrono con mayoría.

### 3.5 Fallos y elección

- Modelo *crash-stop*, sin bizantinos, 3 servidores, quórum 2.
- Heartbeat cada 1 s; timeout de 5 s.
- Si un secundario no recibe heartbeat, inicia elección con término `term + 1`.
- Gana el candidato vivo con menor `id` que obtenga 2 votos y tenga el `last_seq` más alto; si hay empate de `last_seq`, gana el menor `id`.
- El nuevo primario anuncia `COORD`, los clientes se reconectan y el antiguo primario, si vuelve, actúa como secundario y recibe `SNAP`/log.
- Los clientes reintentan la última operación con el mismo `op_id`; el servidor deduplica por `(user, op_id)` para no aplicar dos veces.

### 3.6 Alternativas descartadas

- **Replicación activa:** exige *total order broadcast* y consenso; más coste para una prueba de concepto.
- **Lecturas en secundarios:** mejora el rendimiento, pero complica la linealizabilidad; el primario sirve todas las lecturas.
- **Notificaciones por polling:** más simple, pero no cumple el requisito de notificación del servidor y añade latencia.
- **Base de datos externa:** SQLite embebido es suficiente para 3 réplicas y simplifica la demo.

---

## 4. Milestones

Dependencias: `M0 → M1 → M2 → M3 → M4 → M5 → M6`. M3 y M4 pueden solaparse con M5 en dos pistas si hay tres personas, pero la integración se hace en el orden indicado.

| Milestone | Resultado demostrable | Esfuerzo orientativo |
| --- | --- | --- |
| M0 | Baseline congelado y material de referencia ordenado | 0,5 persona-día |
| M1 | Estado y protocolo preparados para revisiones y manifiesto | 2 persona-días |
| M2 | Fase 1 completa: cliente y servidor reconciliados sin conflictos silenciosos | 2 persona-días |
| M3 | Réplica pasiva con R-broadcast y 3 servidores consistentes | 4 persona-días |
| M4 | Failover automático y reincorporación | 3 persona-días |
| M5 | Ficheros compartidos y notificaciones entre 2 clientes | 3 persona-días |
| M6 | Memoria, presentación, demo y release | 3 persona-días |

Estimación de ingeniería con tests y documentación incluidos. La dedicación estimada por el curso es de 20 h por miembro; si el calendario aprieta, el orden de recorte es: reincorporación automática de réplicas (M4), copias de conflicto automáticas (M5) y CI (M0). Nunca se recorta la demo de failover ni la memoria.

### M0 — Baseline y referencias

**Objetivo:** partir de un estado reproducible y dejar claro qué material es local y qué se versiona.

Tareas:

- [ ] Crear rama `feat/final-project` desde `main` y trabajar cada milestone en una rama/worktree propia.
- [ ] Añadir `docs/ref/` a `.gitignore`; si el grupo necesita compartirlo, migrarlo a Git LFS en un commit separado.
- [ ] Añadir `docs/ref/README.md` con el índice de fuentes, fecha de descarga y licencia/uso.
- [ ] Verificar baseline: `python -m unittest discover -s tests -v`, `python -m ruff check .`, `mkdocs build --strict`.
- [ ] Añadir un workflow de CI que ejecute tests y `ruff` en cada push y PR (hoy solo hay workflows de docs, Docker y release).

**Criterio de salida:** baseline verde, referencias localizadas y CI ejecutando tests.

### M1 — Fundamentos: estado, revisiones y manifiesto

**Objetivo:** introducir metadatos y reconciliación sin romper el protocolo actual.

Ficheros:

- Crear: `file_store.py`, `client_state.py`, `tests/test_file_store.py`, `tests/test_client_state.py`, `tests/test_protocol.py`.
- Modificar: `szasar.py`, `config.py`, `serv_fich_multithread.py`, `sync_client.py`, `docs/protocol.md`, `docs/configuration.md`.

Tareas:

- [ ] Implementar `FileStore` con SQLite y API `put/get/stat/delete/manifest`, incluyendo lápidas y validación de paths.
- [ ] Añadir `SYNC`, `STAT` y los campos opcionales `rev`/`hash` a `UPLO` en `szasar.py` y en el servidor.
- [ ] Añadir límite de longitud de línea a `recvline` y tests de framing (línea vacía, CRLF partido, línea demasiado larga).
- [ ] Implementar `ClientState` con carga/guardado atómico y tests de reconciliación.
- [ ] Añadir tests de store: revisión incremental, hash estable, borrado lógico, aislamiento entre usuarios y path traversal.
- [ ] Servir `SYNC` desde el estado actual del sistema de ficheros si la base aún no existe (migración de instalaciones existentes).

**Criterio de salida:** protocolo antiguo sigue funcionando; `SYNC` devuelve un manifiesto coherente; tests nuevos verdes.

### M2 — Fase 1 completa y subidas con conflicto

**Objetivo:** cliente que reconcilia al arrancar y servidor que nunca pierde una versión por una subida concurrente.

Ficheros:

- Modificar: `sync_client.py`, `file_store.py`, `serv_fich_multithread.py`, `docs/architecture.md`, `docs/limitations.md`.
- Crear: `tests/test_sync_client.py`, `tests/test_conflicts.py`.

Tareas:

- [ ] Al arrancar, el cliente descarga el manifiesto, sube solo ficheros nuevos o con hash distinto y descarga los ausentes.
- [ ] Ignorar eventos causados por descargas propias usando `ClientState`, no solo una ventana temporal de 2 s.
- [ ] Enviar `rev` base y hash en cada subida; el servidor responde `OK<rev>` o `OK<rev>\t<conflict_path>`.
- [ ] Implementar copia de conflicto con nombre `stem (conflict <client-id> <YYYYmmdd-HHMMSS>)suffix`, con contador si ya existe.
- [ ] Propagar borrados solo para paths previamente sincronizados; no borrar ficheros locales nuevos que aún no se han subido.
- [ ] Tests: arranque con servidor vacío, arranque con servidor con ficheros, modificación local, borrado local, dos subidas concurrentes y renombrado.

**Criterio de salida:** dos clientes que arrancan y operan secuencialmente convergen sin bucles de subida; los conflictos generan copia y no sobrescritura silenciosa.

### M3 — Replicación pasiva y R-broadcast

**Objetivo:** un primario y dos secundarios aplican las mismas operaciones en el mismo orden.

Ficheros:

- Crear: `replication.py`, `server_runtime.py`, `tests/test_replication.py`, `tests/test_server_runtime.py`.
- Modificar: `serv_fich_multithread.py`, `file_store.py`, `config.py`, `docs/architecture.md`, `docs/protocol.md`, `compose.yaml`.

Tareas:

- [ ] Añadir configuración `SERVER_ID`, `SERVER_ROLE=primary|secondary`, `SERVER_PEERS=id@host:port,...`, `HEARTBEAT_INTERVAL`, `FAILURE_TIMEOUT`.
- [ ] Implementar `create_server(config)` para arrancar en un puerto efímero en tests y mantener el entrypoint actual.
- [ ] Implementar `ReliableBroadcast`: deduplicación por `(term, seq)`, ACK, retransmisión y entrega en orden.
- [ ] Implementar el log persistente de operaciones y la aplicación determinista en `FileStore`.
- [ ] El primario espera quórum 2/3 antes de responder; si no hay quórum, responde `ER12` y no confirma.
- [ ] Los secundarios rechazan operaciones de cliente con `ER13` e informan del primario actual.
- [ ] Ampliar `ER_MSG` en `cli_fich.py` con los códigos 12 (sin quórum) y 13 (no soy el primario).
- [ ] Tests: 3 réplicas en threads, 20 mutaciones, mismo hash de estado en las 3; duplicado no se aplica dos veces; secundario caído no bloquea con quórum; sin quórum se rechaza.

**Criterio de salida:** estado idéntico en las tres réplicas tras una secuencia de operaciones y test de linealizabilidad básica con dos clientes.

### M4 — Detección de fallos, elección y reincorporación

**Objetivo:** el servicio sobrevive a la caída del primario sin perder operaciones confirmadas.

Ficheros:

- Crear: `election.py`, `tests/test_election.py`, `tests/test_failover.py`, `scripts/demo_failover.py`.
- Modificar: `server_runtime.py`, `replication.py`, `cli_fich.py`, `sync_client.py`, `config.py`, `docs/architecture.md`.

Tareas:

- [ ] Heartbeats, timeout y máquina de estados `Follower/Candidate/Leader` con términos.
- [ ] Elección por menor `id` con quórum y desempate por `last_seq`; *fencing* de primarios antiguos.
- [ ] Reconexión de clientes: descubrir el primario actual y reintentar la operación pendiente con el mismo `op_id`.
- [ ] Reincorporación: `SNAP` desde el primario y aplicación del log hasta `last_seq`.
- [ ] Demo: arrancar 3 servidores y 2 clientes, matar el primario, verificar que una subida posterior funciona y que no se pierde lo confirmado.
- [ ] Tests: caída del primario, caída de un secundario, doble candidato, retorno del primario antiguo y operación duplicada.

**Criterio de salida:** failover en menos de 5 s en la demo; suite de failover verde y sin *split-brain* con quórum.

### M5 — Ficheros compartidos y notificaciones

**Objetivo:** cerrar la fase 3: varios clientes comparten ficheros y reciben los cambios del servidor.

Ficheros:

- Crear: `notification_hub.py`, `remote_watcher.py`, `tests/test_notifications.py`, `tests/test_shared_files.py`.
- Modificar: `serv_fich_multithread.py`, `server_runtime.py`, `sync_client.py`, `cli_fich.py`, `szasar.py`, `docs/protocol.md`, `docs/architecture.md`.

Tareas:

- [ ] Registrar conexiones `SUBS` por usuario y limpiar suscripciones al desconectar.
- [ ] Tras cada mutación confirmada, enviar `UPDT` a los demás clientes del usuario (no al originador).
- [ ] En el cliente, hilo de notificaciones que consulta `STAT` y descarga/borra; supresión de ecos por `rev` y `ClientState`.
- [ ] Reconciliación al reconectar: `SYNC` completo y aplicación de diferencias.
- [ ] Tests: cambio en cliente A visible en B en menos de 2 s, borrado en A visible en B, conflicto entre A y B, cliente B desconectado y reconectado.
- [ ] Test de no-regresión: notificaciones siguen funcionando tras failover y con el secundario reincorporado.

**Criterio de salida:** los dos clientes de la demo convergen tras crear, modificar, borrar y conflictuar ficheros; la notificación llega en menos de 2 s.

### M6 — Memoria, presentación, demo y release

**Objetivo:** entregar y defender el proyecto.

Ficheros:

- Crear: `docs/report.md` (fuente de la memoria), `docs/demo.md`, `scripts/demo.sh`, `docs/presentation/outline.md`.
- Modificar: `docs/index.md`, `docs/limitations.md`, `scripts/build_pdf.py`, `README.md`, `mkdocs.yml`.

Tareas:

- [ ] Completar la memoria con la estructura exigida: problema/objetivos, enfoque/arquitectura, decisiones con referencias a fichero:línea, pruebas/resultados, conclusiones y pendientes.
- [ ] Añadir diagramas: componentes, secuencia de mutación, secuencia de failover y modelo de datos.
- [ ] Actualizar `docs/limitations.md` con lo no implementado y justificarlo (la rúbrica valora explicar lo que falta).
- [ ] Preparar la presentación de 15 minutos: 3 bloques, uno por miembro, con demo de 3 minutos.
- [ ] Ensayar la demo dos veces y dejar un guion reproducible (`scripts/demo.sh`).
- [ ] Generar PDF con `python scripts/build_pdf.py`; actualizar `PAGES` si se añaden páginas.
- [ ] Tag `v1.0.0` y verificar bundles de cliente y servidor.

**Criterio de salida:** memoria PDF, presentación ensayada, demo reproducible y release publicado.

---

## 5. Distribución del trabajo (3 personas)

| Pista | Responsabilidad | Milestones |
| --- | --- | --- |
| A — Cliente y sincronización | `client_state.py`, `remote_watcher.py`, `sync_client.py`, tests de cliente | M1, M2, M5 |
| B — Servidor y replicación | `file_store.py`, `replication.py`, `election.py`, `server_runtime.py` | M1, M3, M4 |
| C — Calidad y entrega | Protocolo, tests de integración, CI, docs, memoria, demo | M0–M6 |

Regla de integración: cada PR actualiza `docs/protocol.md` y `docs/architecture.md` en el mismo commit que el cambio de comportamiento. Ningún milestone se cierra sin su test de aceptación y sin revisión cruzada de otra persona.

---

## 6. Estrategia de pruebas y matriz de aceptación

### 6.1 Niveles

- **Unitarios:** framing, `FileStore`, `ClientState`, nombres de conflicto, configuración y elección.
- **Integración:** servidor real en puerto efímero y directorio temporal; cliente `SyncWorker` real con `watchdog`.
- **Sistema:** 3 servidores + 2 clientes en threads o procesos, fallo del primario y reconexión.
- **No funcionales:** arranque en menos de 2 s, notificación en menos de 2 s, failover en menos de 5 s, sin pérdida de operaciones confirmadas.

Utilidades de test: `wait_until(predicate, timeout=5)`, puertos `0`, directorios `tempfile.TemporaryDirectory`, inyección de reloj/timeouts en `election.py` y `replication.py` para evitar sleeps frágiles.

### 6.2 Matriz requisito → test

| Requisito | Test |
| --- | --- |
| Manifiesto y reconciliación | `tests/test_client_state.py::test_startup_reconciles_manifest` |
| Conflicto sin sobrescritura | `tests/test_conflicts.py::test_concurrent_upload_creates_conflict_copy` |
| Mismo orden en réplicas | `tests/test_replication.py::test_replicas_converge_after_mutations` |
| Sin quórum no se confirma | `tests/test_replication.py::test_primary_rejects_without_quorum` |
| Failover sin pérdida | `tests/test_failover.py::test_new_primary_preserves_committed_operations` |
| Notificación entre clientes | `tests/test_shared_files.py::test_change_propagates_to_second_client` |
| Borrado remoto | `tests/test_shared_files.py::test_delete_propagates_to_second_client` |
| Reconexión de cliente | `tests/test_shared_files.py::test_offline_client_reconciles_on_reconnect` |
| Path traversal | `tests/test_file_store.py::test_rejects_path_outside_user_root` |

### 6.3 Comandos de verificación

```sh
python -m unittest discover -s tests -v
python -m ruff check .
mkdocs build --strict
python scripts/demo_failover.py
```

---

## 7. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
| --- | --- | --- |
| La replicación consume el tiempo del proyecto | Alto | Alcance reducido: 3 réplicas, localhost, lecturas solo en primario, quórum 2/3, configuración manual. |
| Tests de timing frágiles | Medio | Inyección de timeouts, `wait_until`, puertos efímeros y evitar sleeps fijos. |
| Pérdida de operaciones en failover | Alto | Log persistente, `op_id` idempotente, confirmación tras quórum y `SNAP` al reincorporar. |
| Documentación desactualizada | Medio | Cada PR actualiza protocolo/arquitectura; `mkdocs --strict` en CI. |
| `docs/ref/` infla el repositorio | Bajo | Mantener local o Git LFS; excluir de bundles y del PDF. |
| El informe llega tarde | Medio | Empezar la memoria en M4 con resultados reales; cerrar en M6 con dos ensayos de presentación. |

---

## 8. Entregables del proyecto

- Código en `main` con los tres incrementos y tests.
- `docs/report.md` y PDF final.
- `docs/presentation/outline.md` y material de la presentación.
- `scripts/demo.sh` y `scripts/demo_failover.py`.
- Documentación MkDocs actualizada.
- Release `v1.0.0` con bundles de cliente y servidor.

---

## 9. Siguiente paso

1. Revisar y aprobar este roadmap (orden, alcance y política de `docs/ref/`).
2. Escribir el plan de implementación detallado de M1 con `superpowers:writing-plans`.
3. Crear la rama/worktree de M1 y ejecutar con TDD.

---

## 10. Actualización 2026-10-23

Decisiones cerradas después de revisar el alcance con el grupo:

- Cliente multiplataforma **Windows x64 + Linux x64**; macOS queda fuera.
- Instalación **portable + wizard**; sin instaladores firmados, sin auto-update.
- **TLS obligatorio** en cliente-servidor, réplicas y web admin; sin fallback en claro.
- Registro abierto con roles `admin`/`user` y contraseñas PBKDF2.
- GUI de cliente con Tkinter/ttk.
- Web admin completa con usuarios, shares, settings, estado y step-down de demo.
- Compartición **entre usuarios distintos** con ACL `ro`/`rw`; sin self-share.
- `docs/ref` se versiona en Git normal (42 MB, máximo 7,1 MB) y se excluye de MkDocs junto con `docs/superpowers`.

Roadmap vigente:

| Milestone | Contenido | Horas |
| --- | --- | ---: |
| M0 | Baseline, Git, CI, referencias | 3 |
| M1 | Usuarios/shares/settings, auth, TLS, `SYNC`/`STAT`, outbox | 14 |
| M2 | Reconciliación al arrancar, conflictos, lápidas | 10 |
| M3 | Réplica pasiva, log, quórum, snapshots, TLS/mTLS | 18 |
| M4 | Elección, fencing, failover, reincorporación | 10 |
| M5 | Shares entre usuarios y notificaciones | 14 |
| M6 | GUI de cliente: wizard, login/registro, ajustes, shares, outbox | 40 |
| M7 | Web admin completa con HTTPS | 27 |
| M8 | Memoria, presentación, demo y release | 12 |
| M9 | Bundles portables Windows/Linux, CI de release y docs de instalación | 12 |
| **Total** | | **160** |

Con buffer: **175–190 h** (≈58–63 h/miembro). Riesgo principal: calendario.
Orden de recorte si hiciera falta: web admin completa → extras de GUI →
reincorporación automática → copias de conflicto. No se recortan TLS, wizard,
outbox, demo de failover ni memoria.

M0–M5 están implementados y fusionados. M6 (daemon, IPC local, CLI de control,
GUI Tkinter, bandeja y autostart) está implementado en la rama `feat/m6-gui`;
el plan detallado está en `2026-10-23-m6-gui-daemon.md`. El siguiente paso es el
plan detallado de M7 (web admin HTTPS) y M8 (memoria, presentación, demo y
release).
