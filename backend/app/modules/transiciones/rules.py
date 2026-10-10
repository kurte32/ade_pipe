"""Transition rules. One function per transition; parameters come from catalogs (TDD 7.1).

Each rule returns the list of missing requirements (Spanish, user-facing). Empty list means
the transition is allowed.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Protocol

from app.models import ESTATUS_DOCUMENTOS, ESTATUS_DUENO, ESTATUS_ORDER, ESTATUS_VISITA


class _Contacto(Protocol):
    @property
    def nombre(self) -> str: ...

    @property
    def telefono(self) -> str: ...


class _Visita(Protocol):
    @property
    def frente_m(self) -> object: ...

    @property
    def fondo_m(self) -> object: ...


class _Archivo(Protocol):
    @property
    def tipo(self) -> str: ...

    @property
    def tipo_documento(self) -> str | None: ...

    @property
    def vigente(self) -> bool: ...

    @property
    def estado(self) -> str: ...


class SitioLike(Protocol):
    @property
    def estatus(self) -> str: ...

    @property
    def contacto(self) -> _Contacto | None: ...

    @property
    def visita(self) -> _Visita | None: ...

    @property
    def archivos(self) -> Sequence[_Archivo]: ...


def next_estatus(current: str) -> str | None:
    """The only status a coordinator may advance to from `current`, or None if terminal/unknown."""
    if current not in ESTATUS_ORDER:
        return None
    idx = ESTATUS_ORDER.index(current)
    if idx + 1 >= len(ESTATUS_ORDER):
        return None
    return ESTATUS_ORDER[idx + 1]


def to_dueno_localizado(sitio: SitioLike, required_docs: Iterable[str] = ()) -> list[str]:
    missing: list[str] = []
    c = sitio.contacto
    if c is None:
        return ["Captura el contacto del dueño (nombre y teléfono)"]
    if not (c.nombre or "").strip():
        missing.append("Falta el nombre del dueño")
    if not (c.telefono or "").strip():
        missing.append("Falta el teléfono del dueño")
    return missing


def to_primera_visita(sitio: SitioLike, required_docs: Iterable[str] = ()) -> list[str]:
    v = sitio.visita
    if v is None:
        return ["Captura las medidas del local (frente y fondo)"]
    missing: list[str] = []
    if v.frente_m is None or float(str(v.frente_m)) <= 0:
        missing.append("Falta el frente del local")
    if v.fondo_m is None or float(str(v.fondo_m)) <= 0:
        missing.append("Falta el fondo del local")
    return missing


def to_recepcion_documentos(sitio: SitioLike, required_docs: Iterable[str] = ()) -> list[str]:
    present = {
        a.tipo_documento
        for a in sitio.archivos
        if a.tipo == "documento" and a.vigente and a.estado == "publicado" and a.tipo_documento
    }
    return [f"Falta el documento: {doc}" for doc in required_docs if doc not in present]


RULES: dict[str, Callable[[SitioLike, Iterable[str]], list[str]]] = {
    ESTATUS_DUENO: to_dueno_localizado,
    ESTATUS_VISITA: to_primera_visita,
    ESTATUS_DOCUMENTOS: to_recepcion_documentos,
}


def check(destino: str, sitio: SitioLike, required_docs: Iterable[str]) -> list[str]:
    rule = RULES.get(destino)
    if rule is None:
        return [f"No existe regla para el estatus {destino}"]
    return rule(sitio, required_docs)
