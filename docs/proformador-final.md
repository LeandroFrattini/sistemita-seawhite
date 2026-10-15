# Proformador final (liquidación para Administración)

Documento vivo: se actualiza paso a paso. Todo lo que figura acá lo dijo el usuario; lo marcado como
**PENDIENTE** es una duda sin responder y no se asume.

## Alcance

- Se hace hoy a mano, cuenta por cuenta. Objetivo: automatizarlo, con las mismas reglas.
- Se empieza por **barcos de granos y LPG**. **Otamerica queda para lo último** (no tiene mucho más que las fórmulas normales).
- Se arma en ~8 o 9 pasos, que se definen de a uno. Cada paso se prueba contra un caso real ya cerrado antes de pasar al siguiente.
- Las fórmulas y tarifas ya usadas en el proformador inicial (`app/proformador_calc.py`) se reutilizan donde corresponda.

## Flujo general (lo dicho hasta ahora)

1. Se va el barco.
2. Operaciones completa los datos del barco (ver "Datos del barco").
3. Al completarlos se abre una plantilla de **VOUCHER**. Pedido de la dueña: si no se completa, **no se puede hacer nada
   en la página**; siempre se abre el voucher y no se puede salir hasta completarlo todo, sin excepción.
4. El voucher tiene los conceptos ya cargados: se **tilda o destilda** cada uno, y hay un apartado para **agregar** conceptos.
   (Los vouchers reales los pasa el usuario; se arma concepto por concepto.)
5. Una vez enviado el voucher: si se tilda **Head Tally** se abre **otro voucher** donde se eligen los **turnos** trabajados,
   en base a los horarios de inicio y fin de carga.
   - Turnos fijos de 6 horas: **01:00–07:00 / 07:00–13:00 / 13:00–19:00 / 19:00–01:00**.

## Reglas confirmadas por el usuario

- **Dólar:** divisa del Banco Nación, igual que el proformador inicial (campo `dolar_venta`).
- **LPG** = barcos del line-up **Flammable**. Granos = line-up **Grain**.
- **Bloqueo:** solo al usuario que marcó los datos de ese barco: tiene que completar el voucher sí o sí. No bloquea al resto del equipo.
- **Quién agrega conceptos al voucher:** todos los usuarios de Operaciones y los de Administración.
- **Head Tally:** cada turno se cobra distinto, y el precio también cambia si es sábado, domingo o feriado.
  Los valores son **distintos a los del proformador inicial**: acá ya son costos **FINALES** y las **cargas sociales se suman al final**.
- **Edición:** el voucher se puede editar después de enviado.

## Los 10 pasos (según el usuario; se detalla uno por uno)

1. **Dólar:** divisa BNA por escala. Traerlo del Banco Nación o escribirlo a mano (a veces hace falta el dólar de hasta 5 días atrás; en esos casos es más fácil a mano).
2. **Agencia a facturar:** cada una de las 15 agencias tiene un **fee** y unas **cargas sociales** propias, con un apartado para calcular y cargar los de cada una.
   Por defecto se cargan las agencias que ya están en **Clientes** (no las estibas).
3. **Datos del buque:** trae los horarios que ya se cargaron en la otra planilla (Completar datos). Incluye varios **checkbox** que activan cálculos que van directo a costos
   (se arma planilla por planilla más adelante).
4. **Uso de muelle, uso de fondeadero (si corresponde) y vías navegables.** Vías navegables tiene reglas y límites especiales, no es solo una fórmula.
5. **Amarre y desamarre:** tarifa fija que cambia según el horario en que se hizo.
6. **Habilitaciones de aduana:** varios conceptos con su valor.
7. **Tally:** en base a lo ya completado.
8. **Serenos:** en base al amarre y desamarre del buque; se pueden agregar turnos a mano; sobre el número final se suman las cargas sociales según el cliente.
9. **Según los checkbox del paso 3:** migraciones in/out (en boya o no) y sanitary free pratique en base al TRN del paso 3.
10. **Chequeo general** de toda la proforma, con todo modificable.

## Paso 1 — Dólar

- Divisa BNA. Se guarda **por escala**. Siempre se puede escribir a mano.
- Botón "traer cotización" solo si se encuentra una fuente automática confiable (no hay una confirmada todavía); si no, es manual.
- Queda registrado quién lo cargó y si fue a mano o traído.

## Decisiones tomadas (ronda 2)

- **Voucher vs. estos 10 pasos son dos cosas distintas:** el voucher lo completa Operaciones al irse el barco; los 10 pasos los hace **solo Administración**,
  con la información que "debería" haber cargado Operaciones, pero que ellos también pueden cargar a mano.
- **Fee:** monto fijo en USD por agencia. **Cargas sociales:** generalmente iguales para todas; algunas agencias usan un % distinto
  (hay un % general y cada agencia puede tener el suyo). Se suman **a ambos**, Tally y Serenos, con valores distintos en cada caso.
- **Bloqueo del voucher (Operaciones):** sin salida de emergencia. El usuario que completó los horarios finales del barco queda "clavado" en el voucher hasta completarlo.
  Si cierra la página sin completarlo, aparece una **tarea pendiente para todos**: "COMPLETAR VOUCHER BARCO X", y **cualquier usuario** puede completarlo.
- **Calendario:** botón CALENDARIO donde Administración y el administrador cargan los feriados.
- **Salida:** la proforma se **baja como Excel y el sistema no la guarda**. La página tiene que poder **leer ese mismo Excel** para rehacer o modificar una proforma vieja.
- Cuando el usuario pase los Excel/vouchers reales se ajusta el formato del Excel final.

## Lo ya construido (primera tanda, en `/administracion`)

- **Calendario** (`/administracion/calendario`): alta y baja de feriados por año. Si un feriado cae sábado o domingo, se toma como feriado. Helper `tipo_dia()` en `app/proforma_final.py`.
- **Agencias a facturar** (`/administracion/agencias`): fee en USD y cargas sociales (%) por agencia, más un % general. Salen solas las agencias de Clientes (no las estibas).
- **Proforma final** (`/administracion/proforma-final`): asistente de 10 pasos con los pasos 1 (dólar, a mano) y 2 (agencia) funcionando; 3 a 10 como "se arma más adelante".
  Descarga el Excel (hoja visible + hoja oculta `_estado` con el JSON) y recarga ese Excel. El Excel guarda una **foto** de los valores usados.
- Acceso: administradores y usuarios con permiso de Administración.

## Pendiente de armar

- Voucher y bloqueo (lado Operaciones), voucher de Head Tally, tarea "COMPLETAR VOUCHER".
- Pasos 3 a 10 del asistente. Tarifas con fecha de vigencia.
- Traer el dólar del Banco Nación automáticamente (no hay fuente confiable confirmada).

## Datos del barco (los completa Operaciones al irse el barco)

- Hoy el sistema ya guarda en "Completar datos" (Nuestros barcos → Operados): amarre, inicio de operación, fin de operación, zarpe y cantidad operada.
- **PENDIENTE:** qué datos más hacen falta para el voucher.

## Dudas abiertas

- **PENDIENTE — salida de emergencia:** si el usuario bloqueado no puede completar el voucher (falta un dato, error del sistema), ¿un administrador puede liberarlo, dejando registrado quién y por qué?
- **PENDIENTE — cargas sociales:** porcentaje y sobre qué conceptos se aplican.
- **PENDIENTE — Head Tally:** tabla de precios por turno y tipo de día (semana, sábado, domingo, feriado).
- **PENDIENTE — turno 19:00–01:00:** cruza la medianoche; ¿el tipo de día es el del día en que empieza el turno, o se parte por horas?
- **PENDIENTE — feriados:** de dónde sale la lista (incluye puentes y feriados que cambian cada año).
- **PENDIENTE — usuario bloqueado:** qué pasa si el usuario que marcó el barco no entra más al sistema (licencia, baja).
