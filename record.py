"""Grabador de audio desde la consola con sounddevice (PortAudio)."""

import argparse
import os
import shutil
import time
import wave
from datetime import timedelta

import numpy as np
import sounddevice as sd

DTYPE = 'int32'
SAMPLE_WIDTH = np.dtype(DTYPE).itemsize
CHUNK = 2048
CHANNELS = 1  # Mono
RATE = 48000

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RECORDS_DIR = os.path.join(BASE_DIR, "records")


def next_filename():
    """Devuelve el primer sample_N.wav libre dentro de records/.

    Busca el primer número disponible en lugar de contar archivos, para no
    sobrescribir grabaciones anteriores cuando faltan números por medio.
    """
    os.makedirs(RECORDS_DIR, exist_ok=True)
    n = 1
    while os.path.exists(os.path.join(RECORDS_DIR, f"sample_{n}.wav")):
        n += 1
    return os.path.join(RECORDS_DIR, f"sample_{n}.wav")


def get_input_devices():
    """Devuelve una lista de (índice, nombre) con dispositivos de entrada."""
    return [
        (i, dev["name"])
        for i, dev in enumerate(sd.query_devices())
        if dev["max_input_channels"] > 0
    ]


def list_audio_devices():
    print("Dispositivos de audio disponibles:")
    for i, dev in enumerate(sd.query_devices()):
        print(f"{i}: {dev['name']} (Entrada: {dev['max_input_channels'] > 0})")


def get_free_space():
    """Espacio libre, en bytes, del disco donde se guardan las grabaciones."""
    return shutil.disk_usage(BASE_DIR).free


def estimate_max_duration(free_space_bytes, rate=RATE, channels=CHANNELS,
                          sample_width=SAMPLE_WIDTH):
    """Segundos grabables según el espacio libre y el formato real del WAV."""
    bytes_per_second = rate * channels * sample_width
    return int(free_space_bytes / bytes_per_second)


def format_time(seconds):
    return str(timedelta(seconds=int(seconds)))


def record_audio(duration=None, device_index=None):
    """Graba hasta `duration` segundos o hasta Ctrl+C; devuelve el archivo.

    Los bloques se escriben en disco mientras se graban (no al final), de modo
    que no se acumula toda la grabación en memoria y se conserva lo ya grabado
    incluso si el proceso termina de forma brusca.
    """
    filename = next_filename()
    if device_index is None:
        device_index = sd.default.device[0]

    max_time_str = format_time(estimate_max_duration(get_free_space()))
    print("Grabando audio... (Presiona Ctrl+C para detener)")

    stream = None
    wf = None
    written = 0
    overflows = 0
    result = None
    start_time = time.monotonic()

    try:
        stream = sd.InputStream(
            device=device_index,
            channels=CHANNELS,
            samplerate=RATE,
            dtype=DTYPE,
            blocksize=CHUNK,
        )
        wf = wave.open(filename, "wb")
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(RATE)

        stream.start()
        while True:
            # El segundo valor indica desbordamiento del buffer de entrada.
            data, overflowed = stream.read(CHUNK)
            wf.writeframes(data.tobytes())
            written += data.nbytes
            if overflowed:
                overflows += 1

            elapsed = int(time.monotonic() - start_time)
            time_str = format_time(elapsed)
            if duration is not None:
                print(f"\r{time_str}/{format_time(duration)}", end="", flush=True)
                if elapsed >= duration:
                    break
            else:
                print(f"\r{time_str}/{max_time_str}", end="", flush=True)
    except KeyboardInterrupt:
        print("\nGrabación detenida por el usuario.")
    except Exception as e:
        print(f"\nError durante la grabación: {e}")
    finally:
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        if wf is not None:
            try:
                wf.close()  # Escribe la cabecera WAV definitiva.
            except Exception:
                pass

        if written:
            print(f"\nAudio guardado como {filename}")
            print(f"Datos escritos: {written} bytes  ·  {overflows} desbordamientos")
            result = filename
        else:
            if os.path.exists(filename):
                os.remove(filename)
            print("\nNo se guardó ningún archivo, no hay datos de audio.")

    return result


def main():
    parser = argparse.ArgumentParser(description="Grabador de audio con sounddevice.")
    parser.add_argument("--t", type=int, default=None,
                        help="Duración de la grabación en segundos (opcional, por defecto es indefinida)")
    parser.add_argument("--d", type=int, default=None,
                        help="Índice del dispositivo de entrada")
    parser.add_argument("--ld", action="store_true",
                        help="Listar dispositivos de audio disponibles")
    args = parser.parse_args()

    if args.ld:
        list_audio_devices()
        return

    record_audio(duration=args.t, device_index=args.d)


if __name__ == "__main__":
    main()
