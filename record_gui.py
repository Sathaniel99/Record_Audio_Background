"""Grabador de audio con interfaz gráfica y bandeja del sistema.

- Botones Iniciar / Detener.
- Al minimizar (o cerrar), la ventana se oculta y el icono queda en la bandeja.
- La grabación sigue activa mientras la ventana está oculta.
- El audio se escribe a disco mientras se graba (no solo al detener),
  para no perderlo si el proceso se cierra de forma brusca.
"""

import os
import time
import wave
import threading
import queue
from collections import deque
from datetime import timedelta

import sounddevice as sd
from PIL import Image, ImageDraw
import pystray

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except ImportError:  # pragma: no cover
    raise SystemExit("tkinter no está disponible en esta instalación de Python.")

# Reutilizamos la configuración y las utilidades del script de consola.
from record import DTYPE, SAMPLE_WIDTH, CHUNK, CHANNELS, RATE, get_input_devices, next_filename


def format_time(seconds):
    return str(timedelta(seconds=int(seconds)))


def format_size(num_bytes):
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024 or unit == "GB":
            return f"{num_bytes:.0f} {unit}" if unit == "B" else f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024


def make_tray_image(recording=False):
    """Icono dibujado en memoria: micrófono azul (parado) / rojo (grabando)."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = (229, 57, 53, 255) if recording else (66, 133, 244, 255)

    draw.rounded_rectangle((24, 8, 40, 36), radius=8, fill=color)
    draw.arc((15, 20, 49, 50), start=0, end=180, fill=color, width=4)
    draw.line((32, 48, 32, 55), fill=color, width=4)
    draw.line((23, 55, 41, 55), fill=color, width=4)

    if recording:
        draw.ellipse((46, 5, 60, 19), fill=(229, 57, 53, 255))
    return img


class AudioRecorder:
    """Graba en un hilo de audio y vuelca los datos a disco de forma incremental."""

    def __init__(self, device_index=None):
        self.device_index = device_index
        self.filename = None
        self.running = False
        self.bytes_written = 0
        self.overflows = 0

        self._chunks = deque()
        self._stop_event = threading.Event()
        self._writer = None
        self._stream = None
        self._wave = None
        self._started_at = 0.0
        self._last_duration = 0.0

    @property
    def elapsed(self):
        if self.running:
            return time.time() - self._started_at
        return self._last_duration

    def _callback(self, indata, frames, time_info, status):
        # Este callback corre en el hilo de PortAudio: solo encola bytes.
        # No hacemos E/S de disco ni actualizamos la interfaz aquí.
        if getattr(status, "input_overflow", False):
            self.overflows += 1
        self._chunks.append(indata.tobytes())

    def _writer_loop(self, wf):
        while True:
            while self._chunks:
                try:
                    chunk = self._chunks.popleft()
                except IndexError:
                    break
                wf.writeframes(chunk)
                self.bytes_written += len(chunk)

            if self._stop_event.is_set() and not self._chunks:
                break
            time.sleep(0.05)

    def start(self):
        if self.running:
            raise RuntimeError("Ya hay una grabación en curso.")

        self.filename = next_filename()
        self.bytes_written = 0
        self.overflows = 0
        self._chunks.clear()
        self._stop_event.clear()

        self._wave = wave.open(self.filename, "wb")
        self._wave.setnchannels(CHANNELS)
        self._wave.setsampwidth(SAMPLE_WIDTH)
        self._wave.setframerate(RATE)

        self._writer = threading.Thread(target=self._writer_loop, args=(self._wave,), daemon=True)
        self._writer.start()

        try:
            self._stream = sd.InputStream(
                device=self.device_index,
                channels=CHANNELS,
                samplerate=RATE,
                dtype=DTYPE,
                blocksize=CHUNK,
                callback=self._callback,
            )
            self._stream.start()
        except Exception:
            # Si el dispositivo falla, cerramos todo y borramos el archivo vacío.
            self._stop_event.set()
            self._writer.join(timeout=2)
            self._wave.close()
            if os.path.exists(self.filename) and self.bytes_written == 0:
                os.remove(self.filename)
            self.filename = None
            raise

        self._started_at = time.time()
        self.running = True
        return self.filename

    def stop(self):
        if not self.running:
            return self.filename

        self._last_duration = time.time() - self._started_at
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stop_event.set()
            if self._writer is not None:
                self._writer.join(timeout=5)
            if self._wave is not None:
                self._wave.close()
            self.running = False
        return self.filename


class RecorderApp:
    def __init__(self, root):
        self.root = root
        self.recorder = None
        self.commands = queue.Queue()
        self.tray_icon = None
        self.tray_thread = None
        self._last_tray_image_state = None

        self.root.title("Grabador de audio")
        self.root.geometry("360x330")
        self.root.resizable(False, False)

        self._build_ui()
        self._build_tray()
        self.root.after(100, self._poll)

    # ---------- Interfaz ----------

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=16)
        main.pack(fill="both", expand=True)

        title = tk.Label(main, text="Grabador de audio", font=("Segoe UI", 14, "bold"))
        title.pack(anchor="w")

        self.status_label = tk.Label(main, text="● Detenido", fg="#888888", font=("Segoe UI", 11))
        self.status_label.pack(anchor="w", pady=(10, 0))

        self.time_label = tk.Label(main, text="0:00:00", font=("Consolas", 34, "bold"))
        self.time_label.pack(anchor="w", pady=(4, 0))

        self.file_label = tk.Label(main, text="Archivo: —", font=("Segoe UI", 9), fg="#555555")
        self.file_label.pack(anchor="w")

        self.info_label = tk.Label(main, text="0 B  ·  0 desbordamientos", font=("Segoe UI", 9), fg="#777777")
        self.info_label.pack(anchor="w")

        # Selector de dispositivo de entrada.
        device_frame = ttk.Frame(main)
        device_frame.pack(fill="x", pady=(14, 0))
        ttk.Label(device_frame, text="Entrada:").pack(side="left")
        self._devices = []
        try:
            self._devices = get_input_devices()
        except Exception as exc:
            print(f"No se pudieron listar los dispositivos de audio: {exc}")
        values = [name for _, name in self._devices] or ["No hay dispositivos de entrada"]
        self.device_combo = ttk.Combobox(
            device_frame,
            values=values,
            state="readonly" if self._devices else "disabled",
            width=32,
        )
        default_index = sd.default.device[0]
        selected = 0
        for pos, (idx, _) in enumerate(self._devices):
            if idx == default_index:
                selected = pos
                break
        if self._devices:
            self.device_combo.current(selected)
        self.device_combo.pack(side="left", padx=(8, 0))

        # Botones.
        buttons = ttk.Frame(main)
        buttons.pack(fill="x", pady=(16, 0))
        self.start_button = ttk.Button(buttons, text="▶  Iniciar", command=self._on_start)
        self.start_button.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.stop_button = ttk.Button(buttons, text="■  Detener", command=self._on_stop, state="disabled")
        self.stop_button.pack(side="left", fill="x", expand=True, padx=(4, 0))

        hint = tk.Label(
            main,
            text="Minimiza o cierra la ventana para dejarlo en la bandeja.\nLa grabación continúa.",
            font=("Segoe UI", 8),
            fg="#888888",
            justify="left",
        )
        hint.pack(anchor="w", pady=(14, 0))

        self.root.protocol("WM_DELETE_WINDOW", lambda: self.commands.put("hide"))

    def _selected_device_index(self):
        pos = self.device_combo.current()
        if 0 <= pos < len(self._devices):
            return self._devices[pos][0]
        return None

    def _set_ui_state(self, recording):
        if recording:
            self.status_label.config(text="● Grabando", fg="#e53935")
            self.start_button.config(state="disabled")
            self.stop_button.config(state="normal")
            self.device_combo.config(state="disabled")
        else:
            self.status_label.config(text="● Detenido", fg="#888888")
            self.start_button.config(state="normal")
            self.stop_button.config(state="disabled")
            self.device_combo.config(state="readonly" if self._devices else "disabled")

        # Actualizar el icono de la bandeja solo cuando cambie el estado.
        if self._last_tray_image_state is not recording and self.tray_icon is not None:
            self._last_tray_image_state = recording
            try:
                self.tray_icon.icon = make_tray_image(recording)
            except Exception:
                pass
            self._notify("Grabador de audio", "Grabando..." if recording else "Grabación detenida.")

    # ---------- Bandeja del sistema ----------

    def _build_tray(self):
        self.tray_icon = pystray.Icon(
            "record_audio_background",
            make_tray_image(False),
            "Grabador de audio",
            menu=pystray.Menu(
                pystray.MenuItem("Mostrar ventana", self._tray_show, default=True),
                pystray.MenuItem("Iniciar grabación", self._tray_start),
                pystray.MenuItem("Detener grabación", self._tray_stop),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Salir", self._tray_quit),
            ),
        )
        self._last_tray_image_state = False
        self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        self.tray_thread.start()

    def _notify(self, title, message):
        try:
            self.tray_icon.notify(message, title)
        except Exception:
            pass

    def _tray_show(self, icon=None, item=None):
        self.commands.put("show")

    def _tray_start(self, icon=None, item=None):
        self.commands.put("start")

    def _tray_stop(self, icon=None, item=None):
        self.commands.put("stop")

    def _tray_quit(self, icon=None, item=None):
        self.commands.put("quit")

    # ---------- Acciones ----------

    def _on_start(self):
        if self.recorder is not None and self.recorder.running:
            return
        recorder = AudioRecorder(device_index=self._selected_device_index())
        try:
            path = recorder.start()
        except Exception as exc:
            self._notify("No se pudo iniciar", str(exc))
            if self.root.state() != "withdrawn":
                messagebox.showerror("No se pudo iniciar la grabación", str(exc), parent=self.root)
            return

        self.recorder = recorder
        self.file_label.config(text=f"Archivo: {os.path.basename(path)}")
        self._set_ui_state(True)

    def _on_stop(self):
        if self.recorder is None or not self.recorder.running:
            return
        path = self.recorder.stop()
        self._set_ui_state(False)
        if path:
            size = format_size(self.recorder.bytes_written)
            self.info_label.config(text=f"{size} guardados  ·  {self.recorder.overflows} desbordamientos")
            self._notify("Grabación guardada", os.path.basename(path))

    def _hide_to_tray(self):
        self.root.withdraw()
        self._notify("Grabador de audio", "Sigo en la bandeja. La grabación continúa.")

    def _show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _quit(self):
        if self.recorder is not None and self.recorder.running:
            self.recorder.stop()
        try:
            self.tray_icon.stop()
        except Exception:
            pass
        self.root.destroy()

    # ---------- Bucle de sondeo ----------

    def _poll(self):
        # En Windows 'iconic' es el estado de la ventana minimizada.
        if self.root.state() == "iconic":
            self._hide_to_tray()

        while True:
            try:
                command = self.commands.get_nowait()
            except queue.Empty:
                break
            if command == "show":
                self._show_window()
            elif command == "hide":
                self._hide_to_tray()
            elif command == "start":
                self._on_start()
            elif command == "stop":
                self._on_stop()
            elif command == "quit":
                self._quit()
                return

        if self.recorder is not None:
            elapsed = self.recorder.elapsed
            self.time_label.config(text=format_time(elapsed))
            if self.recorder.running:
                size = format_size(self.recorder.bytes_written)
                self.info_label.config(
                    text=f"{size}  ·  {self.recorder.overflows} desbordamientos"
                )

        self.root.after(100, self._poll)


def main():
    root = tk.Tk()
    app = RecorderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
