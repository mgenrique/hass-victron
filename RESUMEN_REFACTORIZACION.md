# Resumen de Refactorización y Depuración de la Integración Victron
**Fecha:** 9 de Agosto de 2026
**Objetivo:** Actualizar y estabilizar el código para funcionar de manera nativa en versiones modernas de Home Assistant (Python 3.12 - 3.14) con la última versión de la librería `pymodbus`.

A continuación, se detalla el listado de todos los problemas encontrados y solucionados durante la refactorización:

## 1. Sustitución Completa del Decodificador de Modbus
* **Problema:** En las versiones modernas de `pymodbus` (>3.0), la clase `BinaryPayloadDecoder` y las constantes `Endian.Big` fueron eliminadas o reestructuradas, rompiendo por completo la recepción de datos en Python 3.12+.
* **Solución:** Se diseñó e implementó un nuevo decodificador puro de Python nativo llamado `VictronPayloadDecoder` en `coordinator.py`. Utiliza la biblioteca estándar `struct` (`>H`, `>h`, `>I`, `>i`), eliminando la dependencia problemática de `pymodbus.payload` y aumentando el rendimiento y estabilidad de la decodificación.

## 2. Compatibilidad Total con Cambios API de `pymodbus` (slave vs device_id)
* **Problema:** Entre las distintas versiones de la librería subyacente `pymodbus` de HA, el parámetro que define a qué equipo consultar ha cambiado caóticamente de nombre: de `unit=` a `slave=`, luego a `slave_id=` y finalmente a `device_id=`. Esto provocaba bloqueos del tipo `TypeError: unexpected keyword argument`.
* **Solución:** Se programó el método maestro `_call_pymodbus` en `hub.py`. Este método aplica una cascada dinámica de prueba y error, inyectando el ID del dispositivo probando todas las variaciones históricas del parámetro de forma automática, haciendo que la integración de Victron sea ahora 100% inmune a la versión de `pymodbus` que Home Assistant decida utilizar.

## 3. Resolución Crítica de Fallo de Desvío de 'Slave 0'
* **Problema:** En `hub.py`, existía un error lógico grave en la línea `slave = int(unit) if unit else 1`. Dado que el Cerbo GX utiliza el ID `0` por defecto, en Python el número `0` se evalúa como `False`, lo que causaba que todas las consultas y envíos dirigidos al Cerbo GX (baterías, parámetros del sistema ESS, voltajes) fueran desviados sin avisar al esclavo `1`, provocando fallos en todos los sensores del sistema en la UI.
* **Solución:** Se corrigió el evaluador para ser estrictamente explícito (`if unit is not None and str(unit) != ""`), permitiendo que el número `0` llegue de manera intacta a través del bus Modbus hacia el Cerbo GX.

## 4. Estabilización de Conexiones de Red (VictronHub)
* **Problema:** Al ejecutar tareas en múltiples hilos asíncronos y síncronos simultáneos (`SyncWorker`), las peticiones Modbus chocaban, provocando caídas de socket y congelación del loop principal de eventos de HA.
* **Solución:** Se reestructuró la gestión de red creando una instancia única centralizada y protegida por bloqueos (`threading.Lock`) en la clase `VictronHub`. También se añadió auto-reconexión dinámica, comprobando activamente si el socket subyacente de red fue cerrado abruptamente por el dispositivo Cerbo para restaurar la conexión antes de realizar la lectura.

## 5. Prevención de Valores Nulos Corruptos en UI (Ej. -6553.5 Ah)
* **Problema:** En el ecosistema Victron, cuando un equipo físico carece de cierto sensor o parámetro, el registro Modbus devuelve su valor máximo (ej: `65535` en UINT16). El sistema antiguo aplicaba matemáticas de escala a estos valores de error (ej: `65535 / -10 = -6553.5`) y Home Assistant mostraba valores completamente rotos en la interfaz gráfica.
* **Solución:** Se actualizó `coordinator.py` para interceptar de manera temprana los valores Modbus reservados como nulos (`65535`, `32767`, `2147483647`, `4294967295`) **antes** de aplicarles matemáticas de escala. Ahora el coordinador expone correctamente un valor `None`, haciendo que la UI simplemente marque el dispositivo temporalmente como "no disponible" sin corromper historiales ni gráficos.

## 6. Corrección de Nombres de Entidades Retrocompatibles (Sufijo `_0`)
* **Problema:** En versiones anteriores se omitía el sufijo de esclavo para el dispositivo primario. Un error en el código de inicialización de los controles (ej. `binary_sensor.py`, `switch.py`, `button.py`) estaba anexando forzosamente el sufijo `_0` (ej. `binary_sensor.victron_settings_ess_feedinpowerlimit_0`), corrompiendo la compatibilidad con los paneles de interfaz antiguos del usuario.
* **Solución:** Se parcheó la lógica de generación de ID para que vuelva a ignorar el sufijo si el origen proviene del esclavo `0` (reemplazando `(100, 225)` por `(0, 100, 225)`), garantizando que las entidades respeten sus nombres históricos.

## 7. Eliminación de Spam de Logs por Registros Parciales
* **Problema:** Cerbo GX agrupa muchos sensores dispares por bloques Modbus. Cuando Home Assistant consultaba un bloque, y un determinado equipo no lo soportaba, el inversor contestaba correctamente con Modbus Exception Code 10 (`Gateway Path Unavailable`). El sistema de Victron interpretaba esto como una amenaza crítica y emitía alertas `WARNING` constantemente por segundo, paralizando y ensuciando el visor de registros de HA.
* **Solución:** Se degradaron estos registros previstos en `coordinator.py` y `hub.py` al nivel de diagnóstico (`DEBUG`). De este modo, la integración operará de forma transparente y sin ruido visual, reportando solo fallos verdaderos.
