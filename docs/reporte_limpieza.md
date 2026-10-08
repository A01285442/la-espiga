# Reporte de limpieza del Excel

Generado por `seed/limpiar_y_cargar.py` el 08/10/2026 16:44.

## Cifras de control

- Ventas de mostrador capturadas: $36,790 (3 días con captura incompleta).
- Encargos: $29,460 vendidos; $12,040 sin cobrar según el Excel.
- Entregas a crédito: $26,610.
- Total registrado en septiembre: $92,860, contra ~$180,000 que Carmen dice facturar. La diferencia es venta que nunca llegó al Excel.
- Compras: $108,339.
- Saldo por cliente de crédito (al día de la carga): Tienda Lupita $3,460 (vencido $3,460); Abarrotes Don Chuy $2,920 (vencido $2,920); Oxxo Mitras (Sr. Beto) $2,530 (vencido $2,530); Restaurante La Fogata $2,510 (vencido $2,230); Escuela Benito Juárez $2,240 (vencido $2,240); Cafetería El Portal $2,000 (vencido $2,000).

## Ventas de mostrador

- 194 líneas de venta en 30 días.
- 28 fechas escritas como texto ('01/sep') convertidas a fecha.
- 144 totales vacíos o con fórmula: el total se calcula siempre como cantidad×precio (la base lo hace sola con una columna calculada). 0 totales escritos no cuadraban.
- 20 nombres de producto distintos unificados en 15 productos: Bolillo ← Bolillo, bolillo; Concha (sabor no anotado) ← CONCHAS, Concha; Cuernito ← Cuernito, cuerno; Empanada de piña ← Empanada de piña, Empanada piña; Galletas surtidas ← Galletas (kilo), galleta surtida kg.
- 'Concha' y 'CONCHAS' sin sabor se guardan como 'Concha (sabor no anotado)' y ese producto queda desactivado: de aquí en adelante solo se captura vainilla o chocolate.
- Días con '(se fue la luz, no se apuntó todo)' marcados como captura incompleta: 02/09, 12/09, 28/09 (la nota aparece después de las ventas de ese día).

## Encargos

- 34 encargos importados.
- La columna 'Pagado?' (texto libre) se convirtió en pagos: el anticipo es un pago; 'SI', 'pagó en efectivo' y 'transferencia' significan que se liquidó el resto el día de entrega; 'NO', 'pendiente' y 'falta el resto' dejan el saldo pendiente.
- Todos los encargos tienen fecha de entrega anterior a hoy: se marcan como entregados. Si el saldo no es cero, es dinero que el cliente quedó debiendo.
- Teléfonos normalizados a 10 dígitos (venían como '81-2233-4455', '81 9988 7766', etc.).
- Nota al pie no importada: «* los de la libreta de agosto no están aquí, Lupita los tiene». Pedir a Lupita la libreta de agosto.
- Fila 6 (Mariana López, Pastel chocolate 15 pers., letrero 'Feliz cumple Dani'): El Excel decía 'falta 200', pero total $580 − anticipo $200 = $380. Se respetan los números; confirmar con Carmen.
- Fila 11 (Paty (vecina), Pastel 3 leches grande (40) + 2 docenas conchas): El Excel decía 'falta 200', pero total $1,350 − anticipo $100 = $1,250. Se respetan los números; confirmar con Carmen.
- Fila 16 (Mariana López, Pastel de zanahoria mediano): El Excel no tenía total; se usó $420, el precio de otros 'Pastel de zanahoria mediano'. El Excel decía 'falta 200', pero total $420 − anticipo $200 = $220. Se respetan los números; confirmar con Carmen.
- Fila 22 (Fernanda Garza, Rosca de canela 2 pzas): El Excel decía 'falta 200', pero total $180 − anticipo $90 = $90. Se respetan los números; confirmar con Carmen.
- Fila 30 (Mariana López, Rosca de canela 2 pzas): El Excel decía 'falta 200', pero total $180 − anticipo $100 = $80. Se respetan los números; confirmar con Carmen.
- El teléfono 8122334455 aparece en clientes distintos (Jorge Salinas y Fernanda Garza). Se dejan como clientes separados; preguntar si es la misma familia o un error de captura.
- El teléfono 8187654321 aparece en clientes distintos (Carlos Treviño y Sra. Georgina). Se dejan como clientes separados; preguntar si es la misma familia o un error de captura.

## Clientes de crédito

- 45 entregas a crédito importadas.
- 17 formas de escribir a los clientes unificadas en 6 clientes: Abarrotes Don Chuy ← ABARROTES DON CHUY, Abarrotes Don Chuy, Don Chuy, abarrotes don chuy; Cafetería El Portal ← Cafeteria el portal, Cafetería El Portal, El Portal; Escuela Benito Juárez ← Escuela B. Juarez, Escuela Benito Juárez, la escuela; Oxxo Mitras (Sr. Beto) ← Beto Oxxo, Oxxo Mitras (señor Beto); Restaurante La Fogata ← La Fogata, Rest. La Fogata, Restaurante La Fogata; Tienda Lupita ← Tienda Lupita, tienda de la esquina (Lupita).
- La columna 'Saldo' del Excel se ignora: tenía fórmulas aun en filas pagadas. El saldo lo calcula la base: saldo inicial + entregas − abonos.
- 'si' y 'si (efectivo)' = abono por el monto completo; 'parcial 300' = abono de $300; vacío o 'no' = sin pago.
- Don Chuy arranca con saldo inicial de $2,400 (agosto), marcado 'por confirmar'. La Fogata queda con 15 días de crédito; los demás con 7 (cobro semanal).
- Nota al pie: «Don Chuy debe como 2,400 de agosto (preguntarle)».
- Nota al pie: «La Fogata siempre paga a 15 días aunque le digamos los viernes».

## Compras

- 38 tickets importados, total $108,339.
- 9 tickets marcados como posible duplicado (mismo proveedor, ≤1 día, monto ±10%). No se borran: Carmen confirma. Costco 19/09 $2,284; Costco 19/09 $2,253; Costco 19/09 $2,298; Harinera del Norte 01/09 $6,884; Gas Monterrey 16/09 $3,215; Harinera del Norte 02/09 $7,190; Gas Monterrey 16/09 $3,283; Harinera del Norte 25/09 $7,169; Harinera del Norte 26/09 $6,769.
- 2 tickets dicen 'cosas de la casa': marcados como 'incluye gastos personales' (el contador ya advirtió que no deberían facturarse completos).
- Nota al pie: «Todo el ticket se factura a la panadería, aunque traiga cosas de la casa».

## Insumos

- 25 insumos importados. Sin mínimo definido: Azucar glass, Leche evaporada, Sal, Canela molida, Fresas, Colorantes, Charolas (no generan aviso hasta que Carmen defina el mínimo).
- Nota al pie: «Las recetas las saben Toño y Memo, no están escritas». Las recetas se documentan en la fase 2.
