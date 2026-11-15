# python test_deck.py: el botón de delay en Stream Deck y StreamDock, sobre carpetas inventadas. No toca tus botoneras
import json, os, tempfile
import deck

raiz = tempfile.mkdtemp()
deck.APPS = {n: (os.path.join(raiz, n), sub, exe) for n, (_, sub, exe) in deck.APPS.items()}
origen = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'streamdock')
reinicios = []
assert deck.apps() == [] and deck.instalar(origen, 'http://127.0.0.1:8080', 't', reinicios.append) == [], 'sin botoneras no hace nada'

os.makedirs(os.path.join(raiz, 'StreamDock'))
hechas = deck.instalar(origen, 'http://127.0.0.1:8080', 'clave1', lambda exe: reinicios.append(exe) or True)
assert hechas == [{'nombre': 'StreamDock', 'reiniciada': True}] and reinicios == ['StreamDock.exe']
plugin = os.path.join(raiz, 'StreamDock', 'plugins', deck.PLUGIN)
assert open(os.path.join(plugin, 'config.js')).read() == "const BRIDGE = 'http://127.0.0.1:8080', TOKEN = 'clave1';\n"
m = json.load(open(os.path.join(plugin, 'manifest.json'), encoding='utf-8'))
assert m['SDKVersion'] == 1 and m['Name'] == 'Stream Kit', 'a StreamDock le va el manifiesto original'
assert deck.apps() == [{'nombre': 'StreamDock', 'instalado': True}]

# con Stream Deck también: Elgato pide SDK 2, su UUID y la versión mínima
os.makedirs(os.path.join(raiz, 'Stream Deck'))
deck.instalar(origen, 'http://127.0.0.1:8080', 'clave2', lambda exe: False)
e = json.load(open(os.path.join(raiz, 'Stream Deck', 'Plugins', deck.PLUGIN, 'manifest.json'), encoding='utf-8'))
assert e['SDKVersion'] == 2 and e['UUID'] == 'com.streamdelay.toggle' and e['Software'] == {'MinimumVersion': '5.0'}
assert e['Actions'][0]['UUID'].startswith(e['UUID'] + '.'), 'Elgato pide que cada acción empiece con el UUID del plugin'
assert json.load(open(os.path.join(plugin, 'manifest.json'), encoding='utf-8'))['SDKVersion'] == 1
assert [a['instalado'] for a in deck.apps()] == [True, True]
print('ok')
