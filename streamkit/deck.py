"""El botón de delay en una botonera: Stream Deck (Elgato) o StreamDock (Mirabox). Es el mismo plugin en las dos, cada
una con su carpeta. La tecla muestra el estado del delay y al tocarla lo activa o lo saca."""
import json
import os
import shutil
import subprocess
import time

PLUGIN = 'com.streamdelay.toggle.sdPlugin'
APPDATA = os.environ.get('APPDATA', '')
# nombre: carpeta de la app, subcarpeta de plugins, programa
APPS = {
    'StreamDock': (os.path.join(APPDATA, 'HotSpot', 'StreamDock'), 'plugins', 'StreamDock.exe'),
    'Stream Deck': (os.path.join(APPDATA, 'Elgato', 'StreamDeck'), 'Plugins', 'StreamDeck.exe'),
}
SIN_VENTANA = 0x08000000


def apps():
    """Las botoneras instaladas en esta PC y si ya tienen el botón."""
    return [{'nombre': n, 'instalado': os.path.isdir(os.path.join(base, sub, PLUGIN))}
            for n, (base, sub, _) in APPS.items() if os.path.isdir(base)]


def ruta_programa(exe):
    r = subprocess.run(['powershell', '-NoProfile', '-Command',
                        f"Get-CimInstance Win32_Process -Filter \"Name='{exe}'\" | Select-Object -First 1 ProcessId,ExecutablePath | ConvertTo-Json"],
                       capture_output=True, text=True, creationflags=SIN_VENTANA)
    try:
        d = json.loads(r.stdout)
        return d['ProcessId'], d['ExecutablePath']
    except (ValueError, KeyError, TypeError):
        return None


def reiniciar(exe):
    """Cierra y vuelve a abrir la app de la botonera, para que cargue el plugin. Si no estaba abierta, no la abre."""
    p = ruta_programa(exe)
    if not p:
        return False
    subprocess.run(['taskkill', '/F', '/PID', str(p[0])], capture_output=True, creationflags=SIN_VENTANA)
    for _ in range(20):
        if not ruta_programa(exe):
            break
        time.sleep(0.5)
    subprocess.Popen([p[1]], cwd=os.path.dirname(p[1]), creationflags=0x00000008 | 0x00000200, close_fds=True)
    return True


def instalar(origen, panel, token, reiniciar_fn=reiniciar):
    """Copia el plugin a cada botonera instalada, con la dirección del panel y su clave. Devuelve qué hizo en cada una."""
    hechas = []
    for nombre, (base, sub, exe) in APPS.items():
        if not os.path.isdir(base):
            continue
        destino = os.path.join(base, sub, PLUGIN)
        shutil.copytree(os.path.join(origen, PLUGIN), destino, dirs_exist_ok=True)
        with open(os.path.join(destino, 'config.js'), 'w', encoding='utf-8') as f:
            f.write(f"const BRIDGE = '{panel}', TOKEN = '{token}';\n")
        if nombre == 'Stream Deck':  # Elgato pide estos datos en el manifiesto; StreamDock usa el original
            ruta = os.path.join(destino, 'manifest.json')
            with open(ruta, encoding='utf-8') as f:
                m = json.load(f)
            m.update(SDKVersion=2, UUID=PLUGIN[:-len('.sdPlugin')], Software={'MinimumVersion': '5.0'},
                     OS=[{'Platform': 'windows', 'MinimumVersion': '10'}])
            with open(ruta, 'w', encoding='utf-8') as f:
                json.dump(m, f, indent=2, ensure_ascii=False)
        hechas.append({'nombre': nombre, 'reiniciada': reiniciar_fn(exe)})
    return hechas
