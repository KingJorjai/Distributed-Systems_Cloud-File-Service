# TODOs del proyecto

Este documento recoge los puntos pendientes anotados en el código.

## 1. `cli_fich.py`

- [ ] Eliminar el comando de listar, ya no es necesario.
- [ ] Cambios a upload (comentados más abajo).
- [ ] Eliminar el menú, ya no es necesario. Solo dejar logearse.
- [ ] Mensaje Update para que el servidor informe al cliente de cambios en el servidor.
  - [ ] El cliente debe comprobar los cambios y eliminar ficheros o descargar ficheros nuevos o modificados.

## 2. `serv_fich_multithread.py`

- [ ] Eliminar el comando de listar, ya no es necesario.
- [ ] Implementar una base de datos del cliente en el servidor con la estructura: fichero | rev | hash.
- [ ] Cambios a upload (comentados más abajo).
- [ ] Mensaje Update para que el servidor informe a clientes de cambios en su cuenta.

### Cambios a upload previstos

- [ ] Cada vez que el cliente quiere subir un archivo, el servidor debe mandar el rev del archivo.
- [ ] Si la rev es distinta, hay un conflicto (alguien ha modificado el archivo en el servidor).
- [ ] En caso de conflicto, aplicar estrategia update:
  - [ ] Cambiar el nombre del fichero en el servidor a fichero(copia en conflicto XX).extension, siendo XX el número de copia.
  - [ ] La copia nueva pasa a ser la oficial.
  - [ ] Sincronizar la copia en conflicto con el cliente (enviar el nombre del fichero en conflicto). El usuario decidirá qué hacer con eso.
- [ ] Si la rev es igual, el cliente manda el hash del fichero y el servidor lo compara con el hash en la base de datos.
- [ ] Si son iguales, rechaza (positivo) la subida.

## 3. `sync_client.py`

- [ ] Implementar una base de datos del cliente con la estructura: fichero | rev | hash.
- [ ] Cambios a upload (comentados más abajo).

### Cambios a upload previstos

- [ ] Enviar el rev del fichero al servidor.
- [ ] Esperar respuesta.
- [ ] En caso de conflicto:
  - [ ] Almacenar el nombre del fichero en conflicto y, al final, descargarlo.
- [ ] Mandar el hash del fichero.
- [ ] Esperar respuesta.
- [ ] Si el servidor da permiso, subir el archivo.
- [ ] Si ha habido conflicto, descargar el fichero en conflicto.

## Resumen general

Los TODOs principales se centran en tres temas:

1. Eliminar comandos y menús obsoletos.
2. Implementar seguimiento de revisiones y hashes para sincronización fiable.
3. Gestionar conflictos en uploads y notificar cambios con mensajes Update.
