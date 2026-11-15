"""Cuánto consume cada parte de Stream Kit: CPU, memoria y lo que manda por la red. Sin dependencias: le pregunta a
Windows por cada proceso (ctypes). Corre en el proceso de la web y lo muestra /metricas."""
import ctypes
import os
import time
from ctypes import wintypes

k32 = ctypes.windll.kernel32 if os.name == 'nt' else None
NUCLEOS = os.cpu_count() or 1


class Memoria(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [(n, ctypes.c_size_t) for n in (
        'PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage',
        'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]


class MemoriaPC(ctypes.Structure):
    _fields_ = [('dwLength', wintypes.DWORD), ('dwMemoryLoad', wintypes.DWORD)] + [(n, ctypes.c_ulonglong) for n in (
        'ullTotalPhys', 'ullAvailPhys', 'ullTotalPageFile', 'ullAvailPageFile', 'ullTotalVirtual', 'ullAvailVirtual',
        'ullAvailExtendedVirtual')]


if k32:
    k32.OpenProcess.restype = ctypes.c_void_p
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    for f in ('GetProcessTimes', 'K32GetProcessMemoryInfo', 'CloseHandle'):
        getattr(k32, f).argtypes = None
    k32.CloseHandle.argtypes = [ctypes.c_void_p]


def segundos(ft):
    return (ft.dwHighDateTime << 32 | ft.dwLowDateTime) / 1e7  # FILETIME: de a 100 ns


def proceso(pid):
    """(segundos de CPU usados desde que arrancó, bytes de memoria en uso), o None si ya no existe."""
    h = k32.OpenProcess(0x1000, False, pid)  # solo leer datos básicos: no hace falta ser administrador
    if not h:
        return None
    try:
        tiempos = [wintypes.FILETIME() for _ in range(4)]
        if not k32.GetProcessTimes(ctypes.c_void_p(h), *map(ctypes.byref, tiempos)):
            return None
        m = Memoria()
        m.cb = ctypes.sizeof(m)
        k32.K32GetProcessMemoryInfo(ctypes.c_void_p(h), ctypes.byref(m), m.cb)
        return segundos(tiempos[2]) + segundos(tiempos[3]), m.WorkingSetSize
    finally:
        k32.CloseHandle(ctypes.c_void_p(h))


def pc():
    """(segundos ociosos, segundos totales) de todos los núcleos juntos, y la memoria de la PC (usada, total)."""
    ocioso, nucleo, usuario = (wintypes.FILETIME() for _ in range(3))
    k32.GetSystemTimes(ctypes.byref(ocioso), ctypes.byref(nucleo), ctypes.byref(usuario))
    m = MemoriaPC()
    m.dwLength = ctypes.sizeof(m)
    k32.GlobalMemoryStatusEx(ctypes.byref(m))
    return (segundos(ocioso), segundos(nucleo) + segundos(usuario)), (m.ullTotalPhys - m.ullAvailPhys, m.ullTotalPhys)


class Medidor:
    """Los porcentajes salen de comparar con la medición anterior: la primera vuelta de cada parte dice None."""

    def __init__(self, leer=proceso, leer_pc=pc, reloj=time.monotonic):
        self.leer, self.leer_pc, self.reloj = leer, leer_pc, reloj
        self.antes = {}

    def cambio(self, clave, valor, ahora):
        anterior, self.antes[clave] = self.antes.get(clave), (ahora, valor)
        return None if anterior is None or ahora <= anterior[0] else (valor - anterior[1], ahora - anterior[0])

    def medir(self, partes):
        """partes: (nombre, detalle, pid, bytes mandados o None). Devuelve lo que muestra la pantalla."""
        ahora, filas = self.reloj(), []
        for nombre, detalle, pid, enviados in partes:
            datos = pid and self.leer(pid)
            if not datos:
                continue
            fila = {'nombre': nombre, 'detalle': detalle, 'pid': pid, 'ram': datos[1], 'cpu': None, 'kbps': None}
            if (d := self.cambio(('cpu', pid), datos[0], ahora)) and d[0] >= 0:
                fila['cpu'] = round(d[0] / d[1] / NUCLEOS * 100, 1)  # como el Administrador de tareas: % de toda la PC
            if enviados is not None and (d := self.cambio(('red', nombre), enviados, ahora)) and d[0] >= 0:
                fila['kbps'] = round(d[0] * 8 / 1000 / d[1])
            filas.append(fila)
        (ocioso, total), (usada, ram_total) = self.leer_pc()
        uso_pc, anterior = None, self.antes.get('pc')
        self.antes['pc'] = (ocioso, total)
        if anterior and total > anterior[1]:
            uso_pc = round((1 - (ocioso - anterior[0]) / (total - anterior[1])) * 100, 1)
        cpus = [f['cpu'] for f in filas if f['cpu'] is not None]
        return {'partes': filas, 'total': {'cpu': round(sum(cpus), 1) if cpus else None, 'ram': sum(f['ram'] for f in filas)},
                'pc': {'cpu': uso_pc, 'ram': usada, 'ram_total': ram_total}, 'nucleos': NUCLEOS}
