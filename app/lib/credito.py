"""Cálculos de cuentas por cobrar que no conviene hacer en SQL: antigüedad del saldo.

Regla: los abonos pagan primero lo más viejo (saldo anterior, luego las
entregas por fecha). Lo que queda sin cubrir es lo que el cliente debe, y cada
entrega vence en fecha + días de crédito del cliente.
Los totales deben coincidir con la vista v_saldos_credito (hay prueba de eso).
"""

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass
class Cargo:
    fecha: date | None          # None = saldo anterior a septiembre
    descripcion: str
    monto: float
    vence: date | None          # None = ya vencido (saldo anterior)
    pendiente: float = 0.0


def pendientes_por_antiguedad(saldo_inicial: float, entregas: list[tuple[date, str, float]],
                              total_abonado: float, dias_credito: int) -> tuple[list[Cargo], float]:
    """Devuelve (cargos que siguen sin pagar, saldo a favor del cliente)."""
    cargos = []
    if saldo_inicial > 0:
        cargos.append(Cargo(None, "Saldo anterior", saldo_inicial, None))
    for fecha, descripcion, monto in sorted(entregas, key=lambda e: e[0]):
        cargos.append(Cargo(fecha, descripcion, monto, fecha + timedelta(days=dias_credito)))

    por_aplicar = total_abonado
    for cargo in cargos:
        aplicado = min(por_aplicar, cargo.monto)
        cargo.pendiente = cargo.monto - aplicado
        por_aplicar -= aplicado
    return [c for c in cargos if c.pendiente > 0], por_aplicar


def vencido(cargos: list[Cargo], hoy: date) -> float:
    return sum(c.pendiente for c in cargos if c.vence is None or c.vence <= hoy)


def proximo_vencimiento(cargos: list[Cargo], hoy: date) -> date | None:
    futuros = [c.vence for c in cargos if c.vence is not None and c.vence > hoy]
    return min(futuros) if futuros else None


def vencido_desde(cargos: list[Cargo], hoy: date) -> date | None:
    """Fecha del cargo vencido más viejo (para decir 'debe desde el 03/09')."""
    vencidos = [c for c in cargos if c.vence is None or c.vence <= hoy]
    if not vencidos:
        return None
    return vencidos[0].fecha
