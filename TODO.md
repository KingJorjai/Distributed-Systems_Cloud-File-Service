# Trabajo pendiente

Estado actual: M0–M8 implementados y publicados como `v0.11.3`. Queda la
validación manual final y el tag `v1.0.0`.

## Validación final

- [ ] Abrir la GUI en un escritorio Linux real y comprobar login, subida,
      descarga, cierre a bandeja, mostrar, pausar/reanudar, salir y autostart.
- [ ] Repetir la comprobación visual con el bundle de Windows x64.
- [ ] Revisar el informe, la presentación y los PDFs finales.
- [ ] Crear `v1.0.0` solo cuando la validación anterior esté completa.

## Endurecimiento para producción

- [ ] Rate limiting y recuperación de cuentas.
- [ ] Auditoría administrativa persistente.
- [ ] Snapshots por chunks y límites de tamaño configurables.
- [ ] Historial de versiones y recolección de basura de lápidas/conflictos.
- [ ] Grupos y ACLs heredadas.
- [ ] Instaladores firmados, auto-update y gestión de secretos con keyring.
- [ ] Rotación de certificados y automatización del despliegue TLS.

Estas mejoras están fuera del alcance de la entrega actual y se detallan en
`docs/limitations.md`.
