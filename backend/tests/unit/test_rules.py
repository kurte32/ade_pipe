from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.models import (
    ESTATUS_DOCUMENTOS,
    ESTATUS_DUENO,
    ESTATUS_PROSPECTADO,
    ESTATUS_VISITA,
)
from app.modules.transiciones import rules


@dataclass
class Contacto:
    nombre: str = "Juan"
    telefono: str = "5512345678"


@dataclass
class Visita:
    frente_m: Decimal | None = Decimal("8.5")
    fondo_m: Decimal | None = Decimal("12")


@dataclass
class Archivo:
    tipo: str = "documento"
    tipo_documento: str | None = "uso_de_suelo"
    vigente: bool = True
    estado: str = "publicado"


def test_dueno_localizado_requires_name_and_phone() -> None:
    """TDD §7.1 minimum fields (pendiente 5: name and phone). Pinned after a mutation that
    removed the phone check survived the suite (audit TST-5)."""
    assert rules.to_dueno_localizado(Sitio(contacto=Contacto(telefono="   "))) == [
        "Falta el teléfono del dueño"
    ]
    assert rules.to_dueno_localizado(Sitio(contacto=Contacto(nombre=""))) == [
        "Falta el nombre del dueño"
    ]
    assert rules.to_dueno_localizado(Sitio(contacto=Contacto(nombre="", telefono=""))) == [
        "Falta el nombre del dueño",
        "Falta el teléfono del dueño",
    ]
    assert rules.to_dueno_localizado(Sitio(contacto=Contacto())) == []


@dataclass
class Sitio:
    estatus: str = ESTATUS_PROSPECTADO
    contacto: Contacto | None = None
    visita: Visita | None = None
    archivos: list[Archivo] = field(default_factory=list)


def test_next_estatus() -> None:
    assert rules.next_estatus(ESTATUS_PROSPECTADO) == ESTATUS_DUENO
    assert rules.next_estatus(ESTATUS_DUENO) == ESTATUS_VISITA
    assert rules.next_estatus(ESTATUS_VISITA) == ESTATUS_DOCUMENTOS
    assert rules.next_estatus(ESTATUS_DOCUMENTOS) is None
    assert rules.next_estatus("descartado") is None


def test_dueno_requires_contact() -> None:
    assert rules.check(ESTATUS_DUENO, Sitio(), []) != []
    assert rules.check(ESTATUS_DUENO, Sitio(contacto=Contacto(nombre=" ")), []) == [
        "Falta el nombre del dueño"
    ]
    assert rules.check(ESTATUS_DUENO, Sitio(contacto=Contacto()), []) == []


def test_visita_requires_measures() -> None:
    assert rules.check(ESTATUS_VISITA, Sitio(), []) != []
    assert rules.check(ESTATUS_VISITA, Sitio(visita=Visita(fondo_m=None)), []) == [
        "Falta el fondo del local"
    ]
    assert rules.check(ESTATUS_VISITA, Sitio(visita=Visita()), []) == []


def test_documentos_requires_every_required_type() -> None:
    required = ["uso_de_suelo", "predial"]
    s = Sitio(archivos=[Archivo(), Archivo(tipo="foto", tipo_documento=None)])
    assert rules.check(ESTATUS_DOCUMENTOS, s, required) == ["Falta el documento: predial"]
    s.archivos.append(Archivo(tipo_documento="predial", vigente=False))
    assert rules.check(ESTATUS_DOCUMENTOS, s, required) == ["Falta el documento: predial"]
    s.archivos.append(Archivo(tipo_documento="predial"))
    assert rules.check(ESTATUS_DOCUMENTOS, s, required) == []


def test_unknown_destination() -> None:
    assert rules.check("entregado", Sitio(), []) != []
