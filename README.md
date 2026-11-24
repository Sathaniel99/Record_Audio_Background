# Grabador de Audio con sounddevice

Grabador de micrófono en Python con **sounddevice** (PortAudio): grabación indefinida o por tiempo definido, selección de dispositivo de entrada, interfaz gráfica con bandeja del sistema y guardado incremental en WAV.

---

## 📋 Características

- Graba audio en formato WAV (mono, 48 kHz, 32 bits).
- Grabación indefinida (Ctrl+C en la consola / botón **Detener** en la interfaz).
- Opción de grabar durante un número determinado de segundos.
- Muestra el tiempo transcurrido, el tamaño de los datos y los desbordamientos de buffer.
- Permite elegir el dispositivo de entrada y listar los disponibles.
- Guarda en `records/sample_N.wav`, usando siempre el **primer número libre** (nunca sobrescribe grabaciones anteriores).
- La interfaz gráfica sigue grabando con la ventana oculta en la bandeja del sistema.
- El audio se **escribe a disco mientras se graba**, tanto en la consola como en la interfaz, así que no se pierde todo si el proceso se cierra de golpe.

---

## 📦 Requisitos

- **Python 3.11 o superior** (probado con Python 3.14.2; `numpy 2.3.3` y `Pillow 13.0.0` exigen Python >= 3.11).
- Dependencias, fijadas en `requirements.txt`: `numpy`, `sounddevice`, `pystray` y `Pillow`.

```bash
python -m pip install -r requirements.txt
```

> En Windows, `sounddevice` incluye PortAudio en el wheel, así que no hace falta compilador. `PyAudio` no publica wheels para Python 3.14/3.15 en Windows, por eso el proyecto se migró a `sounddevice`.

---

## 🛠 Instalación

1. Clona este repositorio o descarga los archivos.
2. Crea y activa un entorno virtual (recomendado):

```bash
python -m venv venv
venv\Scripts\activate
```

3. Instala las dependencias:

```bash
python -m pip install -r requirements.txt
```

4. Ejecuta el script de consola o la interfaz gráfica según las instrucciones de uso.

---

## 🚀 Uso (consola)

| Argumento | Descripción | Ejemplo |
|:----------|:------------|:--------|
| `--t` | Duración de la grabación en segundos (por defecto, indefinida). | `--t 15` |
| `--d` | Índice del dispositivo de entrada (por defecto, el predeterminado). | `--d 2` |
| `--ld` | Lista los dispositivos de audio disponibles. | `--ld` |

Ejemplos:

```bash
python record.py                 # grabación indefinida, detener con Ctrl+C
python record.py --t 15          # grabar 15 segundos
python record.py --ld            # listar dispositivos
python record.py --d 2           # usar el dispositivo con índice 2
```

En grabaciones indefinidas se muestra el tiempo máximo estimado según el espacio libre del disco. Los bloques de audio se escriben a disco sobre la marcha; al detener se indica el total de bytes y los desbordamientos ocurridos.

---

## 🖥 Interfaz gráfica

Una ventana con botones **Iniciar** y **Detener**, selector de micrófono, reloj de grabación, tamaño de los datos y contador de desbordamientos.

### Cómo abrirla

- Doble clic en **`grabador.bat`** (abre sin consola; usa el `venv` local si existe y, si no, busca Python en el PATH).
- O desde la terminal:

```bash
venv\Scripts\python record_gui.py
```

### Bandeja del sistema

- Al **minimizar** o **cerrar** la ventana (✕), esta se oculta y queda un icono de micrófono en el área de notificaciones de la barra de tareas.
- La grabación **continúa** mientras la ventana está oculta. El icono se pone **rojo** cuando está grabando.
- **Clic izquierdo** en el icono: muestra la ventana.
- **Clic derecho**: menú con *Mostrar ventana*, *Iniciar grabación*, *Detener grabación* y *Salir*. *Salir* detiene la grabación antes de cerrar.
- En Windows 11 puede que el icono aparezca primero dentro del menú **∧** de iconos ocultos; arrástralo a la bandeja para fijarlo.

### Diferencias respecto al script de consola

- La captura usa el *callback* de `sounddevice`, por lo que imprimir en pantalla o mover la ventana no puede bloquear la lectura del micrófono (evita desbordamientos).
- Los comandos de la bandeja se envían a la interfaz por una cola, para no llamar a Tkinter desde otros hilos.
- La escritura a disco se hace en un hilo propio con una cola de bloques; el archivo se cierra correctamente al detener.

---

## 📂 Estructura del proyecto

```text
Record_Audio_Background/
├── record.py         # Script de consola y utilidades compartidas
├── record_gui.py     # Interfaz gráfica con bandeja del sistema
├── grabador.bat      # Lanzador de la interfaz (sin consola)
├── requirements.txt  # Dependencias fijadas
└── records/          # Grabaciones (se crea automáticamente)
```

---

## ⚙ Configuración

- Tasa de muestreo (`RATE`): 48000 Hz.
- Canales (`CHANNELS`): 1 (mono).
- Formato (`DTYPE`): `int32` (32 bits por muestra; `SAMPLE_WIDTH = 4`).
- Tamaño del bloque (`CHUNK`): 2048 muestras.

Estos valores están definidos en `record.py` y se comparten con la interfaz gráfica.

---

## 🧠 Desarrollo con vibe-coding y OpenCode

Este proyecto se programó usando **vibe-coding con [OpenCode](https://opencode.ai/)**. Es decir, el desarrollo se llevó a cabo describiendo en lenguaje natural lo que se quería conseguir —«grabar audio en segundo plano», «migrar de PyAudio a sounddevice para Python 3.14», «añadir un icono en la bandeja», «no perder audio si cierro la ventana»— y dejando que OpenCode generara, modificara y revisara el código de forma iterativa.

El proceso seguido fue:

1. Script inicial de consola con PyAudio y argumentos `--t`, `--d` y `--ld`.
2. Migración a `sounddevice` para eliminar la dependencia de compiladores en Python 3.14.
3. Creación de `record_gui.py`: ventana Tkinter, bandeja del sistema con `pystray`, selector de micrófono y escritura incremental con cola + hilo escritor.
4. Creación de `grabador.bat` para lanzar la interfaz sin consola, con fallback a Python del PATH.
5. Revisión final del código y corrección de detalles: nombres de archivo sin sobrescrituras, estimación de espacio con el ancho de muestra real, manejo de errores al abrir el dispositivo y documentación.

> El resultado se verificó localmente (compilación, importación de módulos y lógica de nombres de archivo). La documentación de este README también se mantuvo con OpenCode.

---

## 🔧 Solución de problemas

- **"No Default Input Device"**: conecta un micrófono y compruébalo con `python record.py --ld`.
- **Error `PortAudioError` al usar `--d`**: el índice no corresponde a un dispositivo de entrada; compruébalo con `--ld`.
- **Audio distorsionado o desbordamientos**: prueba a ajustar `RATE` o `CHUNK` en `record.py` y a cerrar otras aplicaciones que usen el micrófono.
- **El icono de la bandeja no aparece**: en Windows 11 revisa el menú **∧** de iconos ocultos.
- **Permisos**: asegúrate de que Python tenga acceso al micrófono y pueda escribir en la carpeta `records`.
