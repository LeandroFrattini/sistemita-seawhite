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

## Voucher = "SERVICE CERTIFICATE" (el que firma el capitán)

Documento de ejemplo recibido (MV LUNA DISCOVERY, Bahía Blanca). Encabezado con nombre del buque, "BAHIA BLANCA port" y fecha; texto
"I, Master of the above mentioned vessel, hereby certify the ... and/or use of the following services and expenses incurred during vessel's ... port of BAHIA BLANCA PORT"
(**la foto está cortada a la derecha: falta el texto completo**); lista de conceptos; leyenda **"<<FOR CHARTERERS ACCOUNT>>"**; firma y sello del capitán.

Conceptos (16), tal como figuran en la foto (**a verificar contra el original**):

1. PORT DUES
2. CHANNEL TOLL
3. TUGBOATS FOR BERTHING / UNBERTHING
4. PILOT SERVICE IN / OUT
5. MOORING / UNMOORING GANG SERVICE
6. HEAD TALLY CLERK EXPENSES
7. WATCHMAN EXPENSES
8. OSRO CERTIFICATE FOR BUNKER
9. CUSTOM OVERTIME FOR BUNKER AT BOUY 11
10. IMMIGRATION EXPENSES IN/OUT
11. SANITARY FREE PRATIQUE
12. TAXI HIRED FOR IMMIGRATION IN/OUT
13. TAXI HIRED FOR SANITARY AUTHORITIES
14. CUSTOM OVERTIME FOR LOADING & CLEARANCE
15. AGENCY EXPENSES
16. BANK COMISION / LAW 25413 / ETC

Reglas: se tilda/destilda cada concepto y se pueden **agregar** conceptos nuevos. Si se tilda HEAD TALLY CLERK EXPENSES se abre el voucher de turnos.
La plantilla **no debe llevar la firma ni el sello** de ningún barco (regla de los documentos).

## Voucher OCEANWAY (`VOUCHER-OCEANWAY.docx`, Word)

Es **otro formato** de Service Certificate (el de OCEANWAY), distinto del de MV LUNA DISCOVERY:

- Encabezado: `MV <BUQUE>` + tab + `BAHIA BLANCA port, <mes> <día con ordinal>, <año>` (ej. "August 17th, 2026").
- Título "SERVICE CERTIFICATE"; texto "I, Master of the above mentioned vessel, hereby certify the employment and/or use of the following services and expenses incurred during vessel's call to the port of BAHIA BLANCA."
- Tabla con 9 renglones (sin "FOR CHARTERERS ACCOUNT"): PORT DUES · CHANNEL TOLL · TUGBOATS FOR BERTHING/UNBERTHING · PILOT SERVICE IN / OUT ·
  MOORING / UNMOORING GANG SERVICE · HEAD TALLY CLERK EXPENSES · **un renglón agrupado** con CUSTOM OVERTIME FOR LOADING / CUSTOM OVERTIME FOR ENTRANCE /
  IMMIGRATION CLEARANCE IN/OUT / SANITARY FREE PRATIQUE · COMPULSORY WATCHMAN EXPENSES · AGENCY EXPENSES · BANK COMISION / LAW 25413 / ETC.
- Pie: línea de puntos para la firma y "Master of M/V <BUQUE>".
- El archivo trae una imagen (logo de OCEANWAY) en sus recursos.

**CUSTOM OVERTIME tiene sub-conceptos** (dicho por el usuario): Entrance, Loading, Permanence, Bunkering. Cada uno se tilda por separado.
Otros conceptos pueden tener sub-opciones del mismo tipo (a definir).

## Respuestas del usuario (ronda 3)

**Cargas sociales:** el 165 % significa **sumar** 165 % al valor: si vale 100, el valor final es 265 (multiplicador = 1 + %/100).
Los dos valores de la columna "Serenos y Encargado": el primero es de **Serenos**, el segundo (encargado) es del **Head Tally**.
Oceanway muestra un solo valor (117 %).

**Fee:** cada agencia tiene varios renglones, escritos **tal cual** en el sistema, agencia por agencia. En la proforma la persona de Administración
**tilda qué fee corresponde** a ese barco y puede **modificar el monto a mano**. A veces el barco solo viene a tomar bunker y se cobra ese fee.

**Nombres:** World Bond = WBL. Abbey Sea, Sea Plate, McLarty, Seven Seas y T&T existen como clientes.

**LDS (amarre y desamarre):**
- Sábado 00:00–07:00 = día hábil de 19 a 07 (50 %).
- Domingo 23:00 = 100 %; lunes 03:00 = noche de día hábil (50 %), salvo que el lunes sea feriado.
- Al costo de **amarre** se le suma **siempre la lancha** (y dos lanchas si la eslora supera 150 m); igual para el desamarre.
- **ESCALA** (colocación, retiro, alquiler diario): solo cuando en el voucher se selecciona **SHORE GANGWAY** (concepto nuevo del voucher). Las chicas de Administración también lo pueden agregar en el paso de amarre.
- **Buque argentino** (tarifa DCI 22): por ahora no se carga; queda para más adelante.

## Ronda 4 (ajustes)

- **Días no laborables:** el calendario distingue **Feriado** y **Día no laborable**. El día no laborable es una distinción para **Head Tally y Serenos**, que cobran distinto ese día.
  Para LDS un día no laborable se toma como día hábil. Si un día no laborable cae sábado o domingo, se toma como sábado o domingo (**a confirmar**); un feriado manda sobre todo.
  Código: `Feriado.tipo`, `app/calendario.py::conjuntos()`, `tipo_dia(d, feriados, no_laborables)`.
- **Barco a proformar:** en el paso 1 ("Barco y dólar") se elige de la lista de **barcos operados** (una fila por agencia a facturar; sin estibas). Al elegirlo se completa la
  agencia (paso 2), se traen los horarios que cargó Operaciones (amarre, inicio y fin de operación, zarpe, cantidad operada) y la fecha de cotización del dólar pasa a ser la de la zarpada (se puede cambiar).
  También se puede escribir un barco a mano. El Excel guarda esa foto del barco.
- **Bloqueo del voucher:** hasta terminar de probar todo **no debe trabar la PC del administrador**. Cuando se construya va a venir **apagado** y lo prende el administrador desde la pantalla de Admin.
- Pantalla de Agencias rediseñada: tabla con los porcentajes en cada fila, editor de fee desplegable por agencia, barra de guardado fija y versión de celular.

## Fee y cargas sociales por agencia (de `FEE.pdf`, "Clientes 2026") — transcripción, A VERIFICAR

Columna "Serenos y Encargado" = cargas sociales (dos valores: serenos / encargado). **PENDIENTE:** qué significa el % (¿multiplicador sobre el costo?).
Cada agencia tiene **varios fee**, de distinto tipo (hay que elegir cuál se aplica en cada proforma).

| Agencia | Serenos / Encargado | Fee |
|---|---|---|
| ABBEY SEA | 165 % / 167 % | FEE bunker USD 450 · FEE ARMADOR 600 · FEE AGENTE USD 1000. Aparte (VENTONITA / BARITINA): USD 1500 - USD 150 |
| ATLAS AGENCIA MARITIMA | (vacío) | FEE USD 300 + gastos 1000 (ver) · FEE BODEGAS USD 300 |
| BLUESTAR COMPANY | 165 % / 167 % | USD 400 FEE BODEGAS · ARMADOR FEE USD 450 MISC USD 150 · FEE USD 800 - MISCELLANEUS USD 250 · CREW USD 60 (EACH ONE) |
| BACK TO BACK | 165 % - 167 % | FEE AGENTES USD 750 - GASTOS USD 120 · FEE PEDIDORES USD 600 - GASTOS USD 120 · COMBUSTIBLE - bodega USD 350 · FEE USD 60 FOR EMBARK/DESEMBARK |
| ECSA SHIPPING | 130 % / 130 % | FEE USD 650 · FEE FOR EMB/DESEMBARK USD 50 · GASTOS USD 100 |
| MARITIMA HEINLEIN | 165 % - 167 % | FEE AGENTES USD 750 · FEE PEDIDORES USD 600 · COMBUSTIBLE USD 350 · FEE USD 60 FOR EMBARK/DESEMBARK · GASTOS USD 120 |
| MC LARTY | 140 % / 140 % | FEE USD 800 + usd 100 · FEE ARMADOR USD 250 · FEE EMB/DESEMBARK USD 50 |
| OCEANWAY | 117 % | FEE ALL INCLUDED USD 1000 · FEE ARMADOR USD 650 |
| SEA PLATE | 165 % - 167 % | FEE USD 700 · FEE EMB/DESEMBARK 50 · GASTOS USD 300 |
| SEVEN SEAS | 165 % - 167 % | USD 450 PEDIDOR - USD 1600 AGENCIA - USD 250 HOLDS |
| SERVICE MANAGEMENT | 165 % - 167 % | FEE USD 1200 - Exp USD 100 · FEE EMB/DESEMBARK USD 60 · Ferni H USD 500 - Orfeas USD 1000 |
| T&T / KRISSAX | 165 % - 167 % | FEE USD 800 - MISCELLANEUS USD 250 · ARMADOR FEE USD 450 MISC USD 150 |
| WORLD BOND | 165 % - 167 % | FEE AGENCIA USD 900 - GASTOS USD 100 · FEE PEDIDORES USD 600 - USD 100 · FEE EMBARK/DESEMBARK USD 70 · BODEGAS FEE USD 375 - BUNKER 450 |

Consecuencia para el diseño: el "fee" de una agencia NO es un solo monto; son **varios renglones con nombre**, y en el paso 2 se elige cuáles aplican.
Los nombres de esta lista no coinciden siempre con los de Clientes (ej. "Back to Back" / B2B, "Bluestar Company" / Blue Star, "Maritima Heinlein" / Heinlein).

## LANCHAS DEL SUR (LDS) — amarre y desamarre (de `LDS.pdf`, "Tarifario 2026"), A VERIFICAR

**Buques extranjeros** (USD):

| | HABIL | EXTRA 50% | EXTRA 100% |
|---|---|---|---|
| AMARRE | 1.900 | 2.850 | 3.800 |
| LANCHA | 1.070 | 1.610 | 2.140 |
| DESAMARRE | 1.900 | 2.850 | 3.800 |

"* eslora de más de 150 lleva dos lanchas". ESCALA: COLOCACION 490 · RETIRO 490 · ALQUILER DIARIO 280. DRAFT: 290 / 435 / 580.

**Buques argentinos (DCI 22)** (USD): AMARRE 1.140 / 1.710 / 2.280 · LANCHA 642 / 963 / 1.284 · DESAMARRE 1.140 / 1.710 / 2.280. ESCALA: colocación 168 · retiro 168 · alquiler diario 168. "* SAB A PARTIR 13 HS".

**Otros servicios LDS (USD):** servicio de grúa, lancha y pontón 1.850 · carga de mercadería + IVA 2.238,50 · OSRO boya 2.880 · OSRO terminal 1.980 · almacenaje 1.000 · transporte de pasajeros 800 · retiro, colocación y alquiler de defensas (por día) 1.300.

**Horarios y recargos:**
- Días hábiles 07:00–19:00: sin recargo (HABIL)
- Días hábiles 19:00–07:00: 50 % (EXTRA 50%)
- Sábados 07:00–13:00: sin recargo
- Sábados 13:00–24:00: 100 % (EXTRA 100%)
- Domingos y feriados 00:00–24:00: 100 % (EXTRA 100%)

**PENDIENTE:** sábado 00:00–07:00 (no figura); si "lancha" se suma a amarre y desamarre; cuándo aplican ESCALA y DRAFT; cómo se elige "buque argentino".

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
