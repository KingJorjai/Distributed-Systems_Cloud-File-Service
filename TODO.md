# TODOs del proyecto

Este documento recoge las funcionalidades que todavía no están implementadas.

## Sincronización bidireccional

- [ ] Añadir un mensaje `UPDATE` para que el servidor informe al cliente de cambios remotos.
- [ ] Descargar archivos nuevos o modificados en el servidor y eliminar del cliente los que ya no existan.

## Versiones y conflictos

- [ ] Implementar una base de datos de sincronización con `fichero | rev | hash` en el cliente y el servidor.
- [ ] Enviar la revisión y el hash durante las subidas.
- [ ] Detectar conflictos y conservar copias con nombres diferenciados.
- [ ] Permitir que el cliente descargue y resuelva las copias en conflicto.

## Seguridad y operación

- [ ] Sustituir las credenciales educativas fijadas en el código por una configuración segura.
- [ ] Añadir cifrado TLS al protocolo TCP.
- [ ] Hacer persistente la cola de cambios para no perder operaciones pendientes al cerrar el cliente.
