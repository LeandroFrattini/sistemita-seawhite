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

## Los 11 pasos (según el usuario; se detalla uno por uno)

1. **Barco y dólar:** se elige el barco operado y la cotización divisa BNA (a mano; a veces hace falta la de hasta 5 días atrás).
2. **Agencia a facturar:** fee (varios renglones, se tildan los que aplican) y cargas sociales (Serenos y Head Tally) de cada agencia.
3. **Datos del buque:** trae todo lo que se cargó (horarios, cantidad) y los datos del buque (TRN, TRB, eslora, manga, puntal, bandera) y los **calados**; todo se puede corregir.
4. **Practicaje** (paso agregado): entrada y salida, con los calados y la **misma tabla de coeficientes** del proformador inicial.
5. **Uso de muelle, uso de fondeadero (si corresponde) y vías navegables.** Vías navegables tiene reglas y límites especiales, no es solo una fórmula.
6. **Amarre y desamarre:** LDS, tarifa fija que cambia según el horario en que se hizo.
7. **Habilitaciones de aduana:** varios conceptos con su valor.
8. **Tally:** en base a lo ya completado (turnos del voucher).
9. **Serenos:** en base al amarre y desamarre; se pueden agregar turnos a mano; sobre el número final se suman las cargas sociales según el cliente.
10. **Migraciones y sanitary free pratique:** según lo que se usó en el voucher (migraciones IN/OUT, en boya o no) y el TRN.
11. **Chequeo general** de toda la proforma, con todo modificable.

Muchos de estos costos ya están predeterminados por fórmulas o costos fijos en el otro proformador (`app/proformador_calc.py`).

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

## Voucher: lo ya construido (ronda 5)

- **Se abre solo** al completar los 5 datos de una agencia en Nuestros barcos → Operados → Completar datos. Las estibas no llevan voucher. Un voucher **por agencia a facturar** (cada fila de Operados).
  Las filas hermanas (mismo barco, otra agencia) quedan pendientes de su voucher. Las filas completadas antes de existir esta función no generan tarea: se abren con el botón **Voucher** de la tabla de Operados.
- **Formatos:** general de Sea White (Excel, REG-AM-36, `app/docgen/templates/voucher.xlsx`) y **Oceanway en Word** (`voucher_oceanway.docx`). Generador: `app/docgen/voucher.py`.
- **Conceptos:** todos tildados de entrada. Tipos: simple (con "AT BUOY 11" opcional), **CUSTOM OVERTIME** con sub-conceptos (Entrance, Loading, Permanence, Bunkering, Clearance, Store list endorsed),
  y migraciones/taxis con **IN y OUT** (cada uno puede ir en boya: si difieren salen en dos líneas). Concepto nuevo **SHORE GANGWAY** (después suma la ESCALA de LDS en el amarre).
  Se pueden **agregar conceptos**, que quedan en una **memoria** para ofrecerlos la próxima vez (con ✕ para olvidarlos).
- **ENVIAR** lo deja disponible para todos (descarga). Se puede seguir editando. Si lleva **Head Tally**, abre la pantalla de **turnos** (01–07, 07–13, 13–19, 19–01), pre-tildados los que cruzan el horario de carga,
  con el tipo de día (hábil, sábado, domingo, feriado, no laborable). El documento del voucher de Head Tally queda pendiente de su formato.
- **Tarea pendiente para todos:** "COMPLETAR VOUCHER BARCO X" en Pendientes, en la lista de Vouchers y en el cartel de la home, hasta que se envía (y se confirman los turnos si lleva Head Tally).
- **Bloqueo:** quien completó los datos queda clavado en su voucher; **viene APAGADO**, se prende/apaga desde Admin → Usuarios. Funciona desde `current_user` (redirige al voucher salvo vouchers, logout, estilos y cambio de clave).
- Menú: **Operaciones → Vouchers** (y en el menú de celular).

## Voucher del Head Tally (`VOUCHER TALLY.xlsx`, REG-AM-39)

- Formato: "COMPULSORY HEAD TALLY CLERK", `M/V <BUQUE>` y "PORT OF BAHIA BLANCA". Tabla con DATE · CHIEF TALLY CLERK (cantidad, siempre 1) · HOURS (`0700-1300`) · actividad (`BERTHING` / `LDG`) · REMARKS.
  La fecha solo va en el primer turno de cada día. Plantilla: `app/docgen/templates/voucher_tally.xlsx`; generador `voucher.tally()`.
- Sale desde la pantalla de turnos del voucher (después de **confirmar** los turnos): cada turno lleva su **actividad**, editable. Por defecto el turno del amarre es BERTHING y los demás LDG.
- Si hay más turnos que filas (26) se agregan filas con el mismo formato.
- La **tabla auxiliar** que traía el archivo a la derecha (columnas J a L, con turnos y valores) **no se copia**: se ve más adelante, al llegar al paso del Tally.
- **Confirmado:** el voucher del Head Tally es **el mismo para todas las agencias** (solo cambian las cargas sociales al calcular).
- **El Head Tally arranca desde el berthing (amarre)**: los turnos se cuentan desde el amarre hasta el fin de la operación (si no hay amarre cargado, desde el inicio de la carga).
  Actividad por defecto: BERTHING hasta que arranca la carga (el turno del amarre y los que terminan antes del inicio) y LDG después; editable.
- **Turno extra:** a veces se suma un turno extra (a precio normal), el del **mooring (amarre)**: se agrega a mano con fecha, turno y actividad (por defecto MOORING) y se marca como "extra".
- **PENDIENTE (a confirmar):** qué otras actividades hay además de BERTHING, LDG y MOORING; si el turno del mooring es siempre el anterior al del berthing.

## Paso 3 — Datos del buque (construido)

- Al elegir el barco en el paso 1 se traen **todos los horarios que cargó Operaciones** (amarre, inicio y final de operación, zarpe) y la **cantidad operada**; en el paso 3 se ven y se **pueden corregir**.
- Apartado para completar el **TRN** (y la **eslora**, que ya hace falta para las lanchas de LDS: más de 150 m = dos lanchas). Si el barco ya está en el historial del Generador de documentos (por IMO) se **trae su TRN y su eslora**; si no, se completan a mano.
  El TRN es la base de varios cálculos de los pasos siguientes (por ejemplo sanitary free pratique).
- **Servicios del voucher:** se muestran los conceptos tildados y los turnos de Head Tally elegidos (con su actividad), como base para los pasos siguientes.
- Los números se escriben como acá: `1.050,50`, `21.173` (punto de miles) o `150,5`.
- El Excel guarda todo eso (horarios, TRN, eslora, servicios y turnos) y se relee.
- **PENDIENTE:** qué otros datos del buque hacen falta (manga, puntal, calados...); si el TRN o la eslora cargados a mano deben guardarse en el historial del barco para la próxima.

## Ronda 6 (practicaje, calados y AT BUOY)

- **Practicaje (paso 4):** misma fórmula y mismas tablas que el proformador inicial (`app/practicaje.py` reutiliza `calcular_pilotage`): UF = eslora × manga × puntal ÷ 800, coeficiente según el calado **en pies**
  (tabla `ProformaPilotageTramo`), recorrido (km) y service fijo, con descuento; si la manga supera 39,9 m van **dos prácticos** (se duplica la tarifa de gobierno). Entrada y salida con su calado cada una.
  El importe se puede **modificar a mano** (queda marcado) y volver al calculado. Un Excel cargado conserva sus importes mientras no se cambien los datos. Solo recorrido Extranjero (I. White–Profertil, un práctico): otros recorridos no están.
- **Calados:** el de entrada se trae de la última escala del Generador de documentos (viene en metros: se pasa a pies); el de salida se completa a mano.
- **No hace falta** guardar el TRN cargado a mano en el historial del barco.
- **AT BUOY 11 solo en migraciones:** se quitó de todos los demás conceptos del voucher (los taxis, el custom overtime, los conceptos agregados, etc. ya no lo llevan).
- Los costos del voucher (migraciones IN/OUT en boya, sanitary free pratique, etc.) alimentan el paso 10.

## Paso 5 — Uso de muelle, fondeadero y vías navegables (construido) y formato de la proforma final

Fórmulas (confirmadas contra 4 proformas finales reales: PORT ALBERNI, SHI DAI 9, DISCOVERER y AMANDA C, que se reproducen **al centavo**):

- **Días:** cada día se divide en 3 bloques: **00–08 = 0,33 · 08–16 = 0,34 · 16–24 = 0,33**. Si el barco está en cualquier parte de un bloque, se cobra el bloque entero.
  Ej.: 15/10 00:30 a 16/10 13:30 = 1,00 + 0,67 = **1,67 días**. Los bloques son [desde, hasta): a las 16:00 en punto ya es el otro bloque (a confirmar).
- **Uso de muelle (PORT DUES)** = USD 0,46 × TRN × días. Igual para Grain y Flammable. Entrada = amarre y salida = zarpe del paso 3 (se pueden cambiar).
- **Uso de fondeadero (ANCHOR DUES)** = USD 0,15 × TRN × días, con la misma lógica de días. Se activa con la casilla **"Tomó bunker en boya"**, con entrada y salida del fondeo.
- **Vías navegables (CHANNEL TOLL)** = USD 2,05 × coeficiente según TRN × toneladas (cantidad operada). Coeficiente: hasta 5.000 = 0,60 · hasta 10.000 = 0,85 · hasta 17.000 = 1,00 · más = 1,15.
  **Solo bunker:** las toneladas pasan a ser el **20 % del TRN** y se multiplica por el **factor de recorrido 0,7** (confirmado con AMANDA C: 2,05 × 20 % × TRN × 0,7).
- Las proformas finales **no redondean** los importes (el proformador inicial redondeaba para arriba): se muestran con 2 decimales.
- Cada concepto: importe **modificable a mano** y casilla **"Va FOR YOUR ACCOUNT"** (por cuenta del armador: figura en el pie, sin impuestos, y no se factura).

Cómo se ve la **proforma final** (4 ejemplos):

- Una hoja con el **nombre de la agencia** (OCEANWAY, BLUE, SEVEN SEAS, AMI, HEINLEIN), más hojas **SERENOS/WATCHMEN** y **TALLY**.
- Encabezado: TRN, carga/shipper, cantidad, ENTRADA y SALIDA con día y hora, DIAS, **CAMBIO VENTA** y **CAMBIO COMPRA**. Título "MV <BUQUE>".
- Renglones numerados, cada uno en **ARS (columna D) y USD (columna E)**. Se pasa de USD a ARS con el cambio venta o compra, o de ARS a USD dividiendo por el cambio (a definir cuál va en cada concepto).
- Conceptos fijos habituales: IMMIGRATION TAX EXPENSES IN/OUT (USD 1.250 por movimiento; 1.875 en boya), FREE PRATIQUE (`(TRN − 1001)/1000 × 6942,9 + 416574` ARS), TAXIS (ARS 160.000 cada uno), CUSTOM HOUSE OVERTIME (USD 125 por turno),
  COMPULSORY SENASA (USD 40–45), MARITIME CENTER (USD 80), **FEE** de la agencia, y **LAW NR 25413 = 1,2 %** de la suma de los renglones (sin el fee).
- Pie **"FOR YOUR ACCOUNT"**: PILOT SERVICE IN/OUT, TUGBOATS IN/OUT, MOORING/UNMOORING (LDS), OSRO; y según la agencia también PORT DUES, CHANNEL TOLL y ANCHOR DUES, "* sin impuestos".
- **TALLY:** sueldos por turno (hábil, sábado, domingo...) × cantidad de tally clerks; **cargas sociales se suman** (117 % → total × 2,17); hoja **SERENOS** igual, más conveyances (movilidad).
- **Respuestas del usuario (ronda 7):**
  1. **Un solo dólar:** todas las conversiones (USD ↔ ARS) usan el dólar cargado en el **paso 1**; no se distingue cambio venta y compra.
  2. **FOR YOUR ACCOUNT va proforma por proforma** (no hay una regla por agencia): queda como casilla en cada concepto.
  3. **LAW NR 25413:** por ahora **monto fijo** (a definir después); se carga en el chequeo general.
  4. **Bloques de días:** a las 16:00 en punto todavía es el bloque anterior; a las **16:01 ya pasa al siguiente** (igual a medianoche: 00:01). Los bloques tienen **otras reglas** que el usuario va a pasar después.

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

## Beneficio por amarre fuera de día hábil en Uso de muelle (regla del Consorcio, confirmada por el usuario)

Solo afecta a **Uso de muelle** (vías navegables va por toneladas; el fondeo no se toca). Se calcula con el amarre y el **inicio de operación**.

- Si el barco amarra **de lunes a sábado entre las 21:00 y las 24:00** (desde las 21:00 en punto), o **un domingo o feriado a cualquier hora**, **y empieza a operar el día hábil siguiente inmediato**, no se cobra ese tramo:
  del día del amarre no se cobra el tercio 16–24 (lunes a sábado) o todo lo que queda del día (domingo o feriado), tampoco los domingos y feriados que haya hasta la operación, y se cobra **desde las 00:00 del día en que arranca la operación**.
- **Día hábil = lunes a sábado que no sea feriado** (el sábado es hábil; domingo y feriado no). Los días no laborables se toman como hábiles. «Siguiente inmediato» = el primer día hábil después del amarre (saltando domingos y feriados).
- **No hay beneficio** si opera el mismo día del amarre, si opera después de ese día hábil siguiente (por ejemplo amarra el martes de noche y opera el jueves), si amarra antes de las 21:00 un día hábil, o si no hay inicio de operación.
- Se aplica de forma **sugerida**: sale tildada la casilla cuando se detecta el caso y se puede destildar (el barco a veces hace otras operaciones).
- En el Excel queda la nota «beneficio por amarre fuera de día hábil: X días no cobrados» y la foto en el estado (`sin_beneficio`, `perdonados`).
- Ejemplos: amarra sáb 17/10 21:30, opera lun 19/10 08:30 → se perdonan 1,33 días (0,33 del sábado + 1,00 del domingo). Amarra mar 20/10 22:00, opera mié 21/10 → 0,33. Amarra dom 18/10 10:00, opera lun 19/10 → 0,67 (los dos bloques que quedan del domingo). Amarra mar 22:00 y opera el jueves → no hay beneficio.
- Cambió respecto de la regla anterior: ahora vale también de lunes a viernes de noche y el domingo/feriado a cualquier hora; en cambio ya no hay beneficio si la operación arranca más tarde que el día hábil siguiente (antes se perdonaba igual el tercio y los fines de semana intermedios).

## Paso 6 — Amarre y desamarre (LDS) (construido)

Código: `app/lds.py` (`calcular`, `costo_servicio`, `escala_costo`), endpoint `POST /administracion/proforma-final/lds`, estado `lds_amarre`, `lds_desamarre` y `escala`.

- Cada maniobra = **servicio + lancha(s)** con el recargo del día y la hora (hábil 07–19 0 %, hábil 19–07 50 %, sábado 00–07 50 %, sábado 07–13 0 %, sábado desde 13 100 %, domingo y feriado 100 %).
  Día no laborable = hábil. Feriados del Calendario.
- **Lanchas:** una, o dos si la eslora supera 150 m; se puede escribir otra cantidad a mano (vacío = automático).
- **Fecha de la maniobra:** el amarre usa el **amarre** del paso 3 y el desamarre el **zarpe**; se pueden cambiar en el paso.
- **Escala (SHORE GANGWAY):** colocación 490 + retiro 490 + alquiler 280 por día. Sale tildada solo si el voucher tiene SHORE GANGWAY; se puede tildar o destildar.
  **Días de alquiler:** por defecto los días de calendario del amarre al desamarre, ambos inclusive (**a confirmar**); se pueden escribir a mano. Sin recargo horario.
- Cada concepto: importe modificable a mano, «Volver al calculado» y casilla FOR YOUR ACCOUNT (mooring suele ir así, pero se decide proforma por proforma).
- **Pendiente:** DRAFT (290 / 435 / 580) y buques argentinos (tarifa DCI 22), no se cargan por ahora.
- **Respuestas del usuario (ronda 8):** días de alquiler de la escala = días de calendario del amarre al desamarre, ambos inclusive (correcto); la escala no lleva recargo horario (correcto);
  la fecha del desamarre es la del **zarpe** (correcto).
- **Uso lancha de draft** (concepto opcional, se agrega a mano con una casilla): **USD 290 hábil · 435 hábil en overtime · 580 domingo** (con el mismo criterio de día y hora que el amarre:
  feriado y sábado desde las 13 también 580). Fecha por defecto: el fin de operación (se puede cambiar). Estado `lds_draft`; sale en el Excel como «Lancha de draft LDS».

## Paso 7 — Habilitaciones de aduana (construido)

Estado `aduana` (`items` + `cuenta_ajena`); `app/proforma_final.py` (`ADUANA_CLAVES`, `_aduana_items`, `aduana_total`). Precio por defecto en `ProformaParametro` `aduana_habilitacion_usd` = **USD 200** (editable en Proformador → Fórmulas).

- Siete renglones: **FOR ENTRANCE · FOR LOADING · FOR PERMANENCE · FOR BUNKERING · FOR FRESH WATER · FOR PROVISIONS** y **uno libre** (se escribe el concepto).
- Cada renglón: tilde, **cantidad** y **precio** (200 por defecto, modificable); el total del renglón y el total del paso se calculan solos (cantidad × precio). Si se escribe una cantidad, el renglón se tilda solo.
- Salen tildados (cantidad 1) los que el voucher trae como «CUSTOM OVERTIME FOR …»; se pueden tildar o destildar y cambiar la cantidad.
- Una casilla para todo el paso: **FOR YOUR ACCOUNT** (por cuenta del armador, no se factura).
- **PENDIENTE (duda abierta):** el voucher hoy tiene CLEARANCE y STORE LIST ENDORSED (y no FRESH WATER ni PROVISIONS). Si hay que cambiar esos dos renglones del voucher, se toca `CUSTOM_SUBS` en `app/docgen/voucher.py`.

## Pasada de UX de todo el asistente (ronda 9)

Pedido del usuario: UX/UI cuidada y a prueba de errores en todo. Cambios:
- **Resumen** en la columna izquierda (cada concepto con su importe, los de FOR YOUR ACCOUNT marcados y fuera del total) y **total parcial siempre a la vista** junto a Anterior / Siguiente (pie pegado abajo).
- **Cartel por paso** debajo del título: «Para completar este paso:» con lo que falta (ámbar) o «Este paso está completo» (verde). Menú de pasos: ✓ completo, ! falta completar (solo si ya se pasó por ahí), pasos 8 a 11 atenuados con «próximamente».
- **Aviso al cerrar o recargar** si hay cambios sin bajar a Excel (el sistema no guarda las proformas). Al bajar el Excel se avisa si quedaron pasos incompletos. Cargar un Excel no marca cambios.
- Al cambiar de paso se **vuelve arriba** y en celular el menú se centra en el paso actual.
- Explicaciones largas de los pasos 4 a 7 pasan a un desplegable **«Cómo se calcula»**; queda una línea corta.
- **Practicaje**: ahora tiene la casilla **FOR YOUR ACCOUNT** (por movimiento).
- Fechas en las tarjetas: una debajo de la otra cuando no entran.
- **Voucher:** conserva CLEARANCE y STORE LIST ENDORSED y suma **FRESH WATER** y **PROVISIONS** (en Oceanway sin STORE LIST ENDORSED, como antes). Un voucher ya guardado no recibe las líneas nuevas.
  El paso 7 muestra las ocho habilitaciones del voucher, en su orden, más el renglón libre.

## Calados en metros (ronda 10)

- En el paso 3 los calados se **cargan en metros** (así trabajan en la oficina); el estado y el Excel siguen guardando **pies** (la tabla del practicaje es en pies, `1 m = 3,28084 pies`).
  Debajo de cada calado se ve el equivalente en pies y el tramo del coeficiente. Hay un desplegable **«Tabla de pies a metros»** con los tramos del practicaje en las dos unidades (marca el tramo del calado cargado).
- El calado de entrada del Generador de documentos ya viene en metros: se muestra tal cual. En el paso 4 el calado aparece en las dos unidades. En el Excel, la nota de la fila de calados trae los metros.
- Se guarda el valor en pies sin releerlo del campo en cada cambio (evita deriva por redondeo).
- **Corrección en Fórmulas:** al guardar, un formulario al que le faltaba el campo «hasta» de un tramo (calado, remolcadores, toneladas) borraba el tope. Ahora solo se cambia si el campo llega
  (campo presente y vacío = «sin tope», a propósito). Detectado porque en la base local los tramos de calado y de remolcadores habían quedado sin tope.

## Tally (encargado) y Serenos — tarifas «serenos y encargado.xlsx» (Cámara Portuaria y Marítima de Bahía Blanca, AGOSTO 2026) — EN ANÁLISIS

**Encargado = Head Tally** (jornal entero, ARS por turno). Básico 192.587,30 (+10 % = 211.846,03). Cada renglón = básico + adicionales + productividad (25 % del básico):
cereal = + insalubridad 30 %; bolsones/materiales = + peligrosidad 50 %; fertilizantes = ambos (80 %); aceite = ninguno. Valor «con 10 %» (columna L = base × 1,10):

| | Aceite | Cereal | Bolsones/Materiales | Fertilizantes |
|---|---|---|---|---|
| Básico (H) | 264.807,53 | 328.361,34 | 370.730,55 | 434.284,36 |
| Extra 100 % | 476.653,55 | 540.207,36 | 582.576,57 | 646.130,38 |
| Extra 150 % | 582.576,57 | 646.130,38 | 688.499,58 | 752.053,39 |

(Las proformas usan 328.361,35 / 540.207,38 / 646.130,40 = tabla de la hoja. Antes del +10 %: cereal 298.510,31 / 491.097,60 / 587.391,25.) El básico solo: 211.846,03; extra 100 %: ×2; extra 150 %: ×2,5.

**Serenos** (ARS por turno de 6 h: 00–06, 06–12, 12–18, 18–24): hábil 06–12, 12–18 y sábado 06–12 · inhábil 00–06, 18–24 y sábados · domingos y feriados.
NORMAL (aceite) 193.493,56 / 290.239,54 / 386.930,38 · INSALUBRE (cereal, fertilizantes, bolsones-materiales) 290.229,31 / 435.353,11 / 580.462,60 · PELIGROSO (amoníaco, gasoil, posta) 348.316,28 / 522.503,33 / 696.633,10.
**Viáticos por turno (conveyances):** 17.588,21 (sitio ADM / sitio 21 / TBB / Cargill / Profertil) · 28.710,71 (Galvan, Moreno sitio 5-2/3, Dreyfus, Posta y Mega, OTA 1, LDC).

**Cómo se arman las hojas de la proforma (verificado contra PORT ALBERNI, SHI DAI 9 y DISCOVERER):**
- TALLY: cuatro renglones «WAGES AT» (cantidad × valor): básico, cereal hábil «H», extra «100» y extra «150». Cada turno del voucher se asigna a uno. Suma × (1 + % tally de la agencia) y se suma al total
  (SHI DAI: 3 × 328.361,35 + 1 × 540.207,38 = 1.525.291,43; × 1,67 = 2.547.236,69; total 4.072.528,12).
- SERENOS: una celda por turno trabajado con la tarifa que corresponde; subtotal × (1 + % serenos) + conveyances (cantidad de turnos × viático del sitio); las cargas NO se aplican a los viáticos
  (PORT ALBERNI: 2.079.905,78 + 2.433.489,76 + 5 × 17.588,21 = 4.601.336,59).

## Pasos 8 (Tally) y 9 (Serenos) — construidos (ronda 11)

Código: `app/personal.py` (reglas y cálculos), tabla `TarifaPersonal` con **vigencia** (se edita en **Administración → Tarifas de Tally y Serenos**: se crea una vigencia nueva con la fecha desde la que rigen los precios y se corrigen los que cambiaron),
endpoints `POST /administracion/proforma-final/tally` y `/serenos`, estado `tally` y `serenos`. Tarifas de agosto 2026 cargadas (encargado, serenos y viáticos), **sin el 10 %** (se usan los valores de la tabla tal cual).

**Tally (Head Tally = encargado)** — los turnos salen del voucher (se pueden quitar, agregar, cambiar el escalón a mano o «traer de nuevo los del voucher»):
- Día de semana: 07–13 y 13–19 = **Básico (H)**; 19–01 y 01–07 = **Extra 100 %**. Sábado: 07–13 = H · 01–07 y 13–19 = 100 % · 19–01 = **150 %**. Domingo: 07–13 y 13–19 = 100 % · 01–07 y 19–01 = 150 %.
  El lunes 01–07 vuelve a ser 100 % (día de semana).
- **Feriado = 3 × el turno básico** de la categoría, todo el día. (Se aplicó igual al día no laborable: **a confirmar**.)
- Categoría de la carga a elegir (**aceite, cereal, bolsones/materiales, fertilizantes**; sin default: hay que elegirla). Precio por escalón de la tabla, editable por escalón.
- Cargas sociales del Tally de la agencia (el % se suma). Total en pesos y en dólares (el dólar único del paso 1).
- Verificado: DISCOVERER (cereal, 2 × H + 1 × 100 %, 167 %) = 3.195.803,31 = la proforma real.
- Estas reglas cambian dos turnos respecto de proformas viejas: sábado 01–07 (era 150, ahora 100 %) y domingo 13–19 (era H, ahora 100 %).

**Serenos** — turnos de 6 h (00–06, 06–12, 12–18, 18–24) **desde el amarre hasta el zarpe** (todos los que el barco toca), que se pueden quitar y a los que se pueden **agregar turnos**: fecha, turno, categoría y cantidad de serenos (todos los que hagan falta):
- La tabla manda: **hábil** = 06–12 y 12–18 de día de semana y sábado 06–12; **inhábil** = 00–06 y 18–24 de día de semana y sábado 00–06, 12–18 y 18–24; **domingo y feriado** = todo el día como domingo.
  (El día no laborable se trató como feriado: **a confirmar**.)
- Categoría: normal, insalubre, peligroso (una general y, por turno, «como arriba» u otra). Precio por turno editable.
- Cargas sociales de serenos sobre los sueldos (**no** sobre los viáticos). **Viáticos por turno**: White (17.588,21: sitio ADM, 21, TBB, Cargill, Profertil) o Galván (28.710,71: Galván, Moreno, Dreyfus, Posta y Mega, OTA 1, LDC) o sin viáticos; se multiplican por la cantidad de serenos.
- Verificado: PORT ALBERNI (5 turnos, 117 %) y SHI DAI 9 (7 turnos, los 7 viáticos de la proforma). Con las reglas nuevas algunos turnos cambian de tarifa respecto de esas proformas (la tabla manda).

Corrección de fondo: los cálculos del asistente (practicaje, muelle, LDS, tally, serenos) ignoran una respuesta vieja si ya hay un pedido más nuevo (dos cálculos seguidos podían pisarse y dejar el total desactualizado).

## Paso 10 — Migraciones y sanitary free pratique (construido) y otros ajustes (ronda 12)

Código: `app/migraciones.py`, endpoint `POST /administracion/proforma-final/migraciones`, estado `migraciones`. Sale tildado lo que dice el voucher (`desde_voucher`: lee las líneas IMMIGRATION, TAXI HIRED FOR IMMIGRATION, TAXI HIRED FOR SANITARY y FREE PRATIQUE).
- **Migraciones IN y OUT** en USD: 1.250 por movimiento; **1.875 si ese movimiento fue en boya** (solo las migraciones van en boya). Valores de `ProformaConceptoFijo` y del parámetro `immigration_boya_usd`.
- **Free pratique** en pesos: `(TRN − 1.001) / 1.000 × 6.942,9 + 416.574` (parámetros `libre_platica_*`). Sin TRN no inventa el importe: avisa.
- **Taxis** (oficial de migraciones IN, OUT y sanidad), en pesos, cada uno: parámetro `taxi_ars` = **222.000** (el de la proforma más reciente, SHI DAI 9; PORT ALBERNI cobró 160.000 → **a confirmar**).
- Importes editables a mano en cada renglón; totales en USD (migraciones) y en pesos (free pratique y taxis, con su equivalente en dólares con el dólar único). Verificado: PORT ALBERNI (free pratique 490.696,40; migraciones 2.500).
- SENASA, Maritime Center, Miscellaneous, Fee y LAW 25413 quedan para el chequeo general (paso 11).

**Las fórmulas viven solo en Administración:** `/administracion/formulas` (antes `/proformador/config/formulas`, que ahora redirige) y `/administracion/tarifas-personal`. Guardar cualquiera de las dos pide la contraseña. Se sacó el botón «Fórmulas» del Proformador.
Acceso: quien tenga el permiso de Administración (o sea admin). Los textos de la proforma final apuntan ahí.

**Barco de prueba:** en el paso 1 hay una opción «★ BARCO DE PRUEBA» con datos de ejemplo completos (horarios, medidas, calados, voucher, turnos y lo usado en migraciones). No se guarda nada en el sistema.

## Paso 11 (Chequeo general) y Excel final con el formato de las proformas (ronda 13)

**Paso 11** — `app/chequeo.py`, endpoint `POST /administracion/proforma-final/chequeo`, estado `chequeo`. Arma la proforma consolidada, en **pesos y en USD** (dólar único del paso 1), con botón «Corregir» en cada renglón (lleva al paso donde se cambia):
- **SENASA, Maritime Center y Miscellaneous**: monto fijo (parámetros `senasa_usd` = 45, `maritime_center_usd` = 80, `miscelaneos_usd` = 250, editables en Administración → Fórmulas; **SENASA: queda en 45 (confirmado)**). Se tildan / se escribe el monto. El SENASA sale tildado si el voucher lo trae; Maritime Center tildado; Miscellaneous apagado.
- **Fee**: los renglones tildados en el paso 2, cada uno con su texto; no entra en la base de LAW.
- **LAW NR 25413** = `law_25413_pct` (1,2 %) de la suma de los renglones que se facturan, **sin el fee** y sin lo que va FOR YOUR ACCOUNT. Importe editable a mano; se puede destildar.
- Renglones libres (concepto, moneda, monto, FOR YOUR ACCOUNT) y las líneas del pie sin importe (TUGBOATS IN/OUT, COMPULSORY OSRO EXPENSES).
- Orden de los renglones como en las proformas: lo de LDS (si se factura), port dues, anchor, channel toll, pilot, tally, serenos, migraciones, free pratique, habilitaciones, taxis, SENASA, Maritime Center, Miscellaneous, libres, fee y LAW.
- Muestra los pasos que quedaron incompletos, con un enlace a cada uno.
- Taxis: se dejan editables a mano (el precio por defecto es 222.000; las chicas lo cambian porque lo calculan distinto).

**Excel final** — `app/docgen/proforma_xlsx.py` + `templates/proforma_final.xlsx` (la proforma de PORT ALBERNI sin datos: membrete, estilos, anchos e imágenes; sin ruta de carpeta, datos de correo ni de quién la guardó). Reemplaza al resumen en una hoja:
- **Hoja de la agencia** (se llama como la agencia): TRN, carga y shipper, entrada y salida (día y hora), DIAS (suma por día, como «=0.33+1+0.33»), CAMBIO (un solo dólar); título «MV …» bajo el membrete; renglones numerados con **pesos (D) y USD (E)** con fórmulas (`=E*$H$3` o `=D/$H$3`) **y valores guardados** (se ven en Vista protegida y en el celular); LAW como `=SUM(...)*1,2/100`; TOTAL; **FOR YOUR ACCOUNT** con su importe en pesos y USD («* sin impuestos» en port dues/channel toll/anchor, «LDS» en lo de LDS); imagen del pie debajo de todo.
- **SERENOS**: grilla de turnos × días (en pesos, rojo el fin de semana y los feriados, las columnas crecen si la estadía pasa de 4 días), nombre de quien cubrió cada turno (campo opcional en el paso 9), SUBT, % de cargas, CONV., TOTAL, **CAMBIO y TOTAL USD**, y el detalle por día («12 A 18: NOMBRE»).
- **TALLY**: «WAGES AT» por escalón (cantidad × valor), cargas sociales, total en pesos, **CAMBIO y TOTAL USD**, y a la derecha los turnos con fecha, horario y escalón (rojo el 150 % y el feriado).
- Hojas ocultas: `_estado` (para volver a cargar la proforma) y `_resumen` (la foto de lo cargado en cada paso, con sus notas).
- Paso 3: campos nuevos **Carga** y **Shipper** (se traen del line-up: `grade` y `shipper`).
- Verificado abriendo los archivos con Excel (hojas e imágenes), con una estadía de 6 días y 20 renglones.
- El Excel viejo (resumen en una hoja) sigue existiendo solo para uso interno sin base de datos (pruebas).

**Pantalla:** las filas de Tally y Serenos pasan a tarjetas cuando hay poco ancho (≤ 1180 px) para que no se pasen del borde; el resumen de la izquierda se llama «Subtotal de los pasos 1 a 10» (el total final está en el paso 11).

## Descargar la proforma (ajuste de la ronda 14)

- Al final del **paso 11** hay un botón grande **«⬇ Descargar Excel de la proforma»** (y en el último paso el botón del pie pasa de «Siguiente» a «Descargar Excel»). Antes solo estaba el de la barra de arriba y en el último paso «Siguiente» quedaba apagado.
- Los mensajes de la descarga salen también junto a ese botón y dicen qué pasó (sesión cerrada, error del servidor, versión simplificada).
- **Red de seguridad:** si el Excel con formato llegara a fallar, se baja el resumen simple con un aviso y el error queda en el registro (`proforma_final`).
- Los caracteres de control (copiar y pegar, datos importados) se limpian de todos los textos: rompían el XML del Excel.

## Ajustes de la ronda 15: «esto sí lo facturamos», taxis y aduanas

- **Cada punto tiene «Esto sí lo facturamos»** (tildado por defecto). Si se destilda, ese renglón **pasa al pie como FOR YOUR ACCOUNT** (con su importe en pesos y USD) y no entra en el total ni en la base de LAW; se vuelve a tildar y vuelve al cuerpo.
  Está en cada paso (practicaje, muelle, fondeadero, vías, amarre, desamarre, escala, draft, cada habilitación, Tally, Serenos, cada migración, cada taxi y el free pratique) y en el **chequeo general** (columna «Lo facturamos», también en la tabla de FOR YOUR ACCOUNT para devolverlo).
  Estado `cuenta_ajena` en cada concepto; un Excel viejo con una sola casilla para todas las aduanas pasa a cada habilitación.
  El fee y LAW no tienen esa casilla (se destildan en el paso 2 y en el chequeo).
- **Taxis (migraciones y sanidad): 160.000** cada uno (parámetro `taxi_ars`; lo ya cargado con 222.000 se corrige una sola vez). Las chicas lo cambian a mano cuando lo calculan distinto.
- **Aduanas (paso 7):** se abre **una tarjeta por cada habilitación que se tildó en el voucher**, con «cuántas fueron» (botones − y +, o escribiendo), precio de cada una y total; se quita con ✕ y se agregan otras con «Agregar otra habilitación». Ejemplo: 6 de carga, 1 de entrada y 2 de permanencia.
- **Versión visible:** arriba de la proforma final figura «versión xxxxxxx» (el commit que está sirviendo Render) para saber si se está viendo lo último.

## Dos tildes en cada punto: «Esto sí lo facturamos» y «FOR YOUR ACCOUNT» (ronda 16)

Cada punto lleva **dos tildes** (no un desplegable), que no pueden estar los dos a la vez:
- **«Esto sí lo facturamos»** tildado (por defecto): se factura, va en el cuerpo de la proforma.
- **«FOR YOUR ACCOUNT»** tildado: figura al pie, por cuenta del armador (no se factura, con su importe en pesos y USD).
- **Los dos destildados: no figura en ningún lado de la proforma**: ni en el cuerpo, ni al pie, ni en el total, ni en la base de LAW; si es el Tally o los Serenos, **tampoco lleva su hoja** (TALLY / SERENOS) en el Excel.
- Estado: `cuenta_ajena` (al pie) y `omitido` (no figura) en cada concepto, nunca las dos (si llegan las dos, manda «al pie»).
- En el **chequeo general** cada renglón tiene las dos columnas con tilde («Lo facturamos» y «FOR YOUR ACCOUNT») y, abajo, una lista plegable **«No figuran en esta proforma»** para volver a incluirlos.
- Lo que no figura no se pide como pendiente en los pasos (por ejemplo, si el practicaje no figura no se exigen sus datos) y no aparece en el resumen.
- **Paso 7 (aduanas) como lista**: una fila por cada habilitación elegida en el voucher, con la cantidad al costado (− / + o escribiendo), el precio de cada una, el total y los dos tildes; se agregan otras con «Agregar otra habilitación». La lista se vuelve a dibujar sola si faltara alguna.

## Muelle y fondeadero no se cobran dos veces el mismo bloque (ronda 17)

Un bloque de 8 horas en el que el barco ya está cobrado en el **muelle** **no se vuelve a cobrar como fondeadero** (sería un costo duplicado): se cobra siempre el de muelle y el fondeadero cobra desde el primer bloque que no esté en el muelle.
Ejemplo: zarpa del muelle a las 16:30 y llega al fondeadero a las 21:00 → el bloque 16–24 de ese día es del muelle y el fondeadero cobra desde las 00:00. Vale también si el fondeo es antes de amarrar (el bloque en que amarra es del muelle).
La tabla de días del fondeadero marca en verde los bloques que ya cobra el muelle y muestra «Días de fondeo en total» y «Días que ya se cobran en el muelle (no se duplican)». Código: `app/muelle.py::calcular` (`solapado`, `dias_brutos`).

## Proformador de Prácticos (en el Proformador inicial)

Cuarto botón del hub del Proformador (`/proformador/practicos`): calcula solo el costo de practicaje, sin armar una proforma. Se cargan eslora, manga y puntal, el calado de entrada y/o de salida (en metros o en pies; los metros se pasan a pies con 3,28084 y 4 decimales, igual que la proforma final) y el tilde «Dos prácticos». Con manga de más de 39,9 m lleva dos prácticos solo y el tilde queda fijo. Usa `practicaje.calcular` (misma fórmula y mismas tablas que el resto; se editan en Fórmulas) y muestra para cada movimiento el desglose (maniobra, navegación, descuento, gobierno, service) y el total entrada + salida.

## Padrón de serenos (Administración → Serenos)

Lista de serenos con apellido y nombre y CUIL, sin tarifa (los precios siguen en «Tarifas de Tally y Serenos»). Se cargaron los 16 de la lista de Administración (una sola vez; lo que se borre después no vuelve). Se agrega, edita y elimina desde `/administracion/serenos`; el CUIL se normaliza a `XX-XXXXXXXX-X`, no se repite y se rechaza si el dígito verificador no cierra. En el paso 9 de la proforma final, cada turno tiene un desplegable con esos nombres (más «Otro» para escribir uno que no esté, y «sin nombre»); el nombre elegido sale en la hoja SERENOS. Las proformas guardan solo el texto del nombre, así que editar o borrar a alguien de la lista no cambia las ya armadas. Falta el equivalente para Encargado / Head Tally.

## Excel de SERENOS (recibos), aparte de la proforma final

Botón «Descargar Excel de serenos» en el paso 11. Arma el libro «SERENOS» de Administración con lo cargado en el paso 9 (`app/docgen/serenos_xlsx.py`, endpoint `POST /administracion/proforma-final/excel-serenos`):

- **Solapas de recibos** (una por categoría, solo las que tienen recibos): ACEITEROS (normal), CEREALEROS (insalubre) y PELEGROSIDAD (peligroso). Si el barco tiene turnos insalubres, los normales van en CEREALEROS, que trae los renglones «s/insalubr».
- **Un recibo por sereno, tramo de 6 horas, solapa y mes.** Los jornales se agrupan por tipo de día (hábil, sábado, domingo/feriado/no laborable) con las mismas reglas y tarifas del paso 9. Importe = jornales × precio; se descuenta jubilación 14 % (redondeada), contribución solidaria 2 % (sin redondear, como el libro original) y obra social 3 % (redondeada); se suma el viático por jornal (White o Galván, el del paso 9, sin descuentos). Un turno con el precio cambiado a mano sale en un renglón aparte marcado con *.
- **RESULTADO**: un renglón por recibo (mes, buque, tramo, sereno, CUIL, total neto, viáticos y días), el total y el total de cada sereno. **CUIL**: la lista de Administración → Serenos. **WATCHMAN**: la misma grilla de la hoja SERENOS de la proforma final (turnos × días, subtotal, cargas sociales, viáticos, total y total en USD).
- Todo con fórmulas y con su valor guardado (Vista protegida). La fecha del recibo es la del día de la descarga.
- **Control**: si lo que suman los recibos (sueldos y jornales) no coincide con el paso 9, no se genera el archivo. Antes de armarlo exige sereno y categoría en cada turno y el viático.
- En cada turno va **un solo sereno** (se sacó la cantidad de serenos del paso 9).
- Los serenos de la solapa CUIL del libro original que faltaban (BENTANCOURT RAUL y TREUQUE MIGUEL) se agregaron a la lista.

## Encargados (Head Tally): Excel de encargados y tope mensual de aportes

- **Lista** en Administración → Encargados (se cargaron Bruno Aceituno y Fernando Navarrete; son dos fijos: la pantalla no tiene alta ni baja, solo editar nombre y CUIL; muestra por encargado el bruto del mes contra el tope). En el paso 8 se elige el encargado de cada turno: **no figura en la proforma final** (ni en el cuerpo ni en las hojas), solo en el Excel de encargados.
- **Excel de encargados** (botón del paso 11, `app/docgen/encargados_xlsx.py`): la declaración jurada del libro de Administración, una hoja con el nombre del barco, por día y turno el encargado con jornal básico, insalubridad, 1era producción, bruto, retenciones (O.S. 3 %, jubilación 11 %, sindical 3 %, ley 3 %) y neto; totales y viáticos. El bruto de cada turno es el precio del paso 8; se reparte en básico / insalubridad / producción con la tarifa vigente (producción = 25 % del básico; insalubridad = diferencia entre la categoría y aceite: cereal 30 %, bolsones 50 %, fertilizantes 80 %). Los viáticos son un monto por día trabajado (parámetro «viatico_encargado_ars» en Fórmulas, 22.933,49).
- **Tope de sueldo bruto**: en Administración → Encargados se carga, mes a mes, el monto (cada mes arranca de cero). Los aportes de O.S. 3 %, jubilación 11 % y ley 3 % se descuentan **turno por turno, tomando cada turno entero**, mientras al encargado le falten **más de $100.000** para el tope; cuando le faltan $100.000 o menos, los turnos siguientes van sin esos aportes (se puede pasar del tope: los encargados lo superan por millones). El aporte sindical 3 % se descuenta siempre. El margen de $100.000 es el parámetro «encargados_margen_ars» en Fórmulas. Cada cambio del tope queda anotado con quién y cuándo (historial). Sin tope cargado para el mes, no se arma el Excel. En cada barco va un solo encargado.
- **Acumulado entre barcos**: al bajar el Excel de un barco se anotan sus turnos (por encargado, fecha, turno y bruto); el bruto acumulado contra el tope se lleva en orden cronológico sobre todos los turnos del mes. Volver a bajar el mismo barco reemplaza lo anotado. El barco de prueba no anota nada. La pantalla de Encargados muestra cómo va el mes (bruto del mes, aportes descontados, tope alcanzado o cuánto falta).

## Resumen de cada sereno

Administración → Serenos → «Resumen» de cada sereno: los barcos que atendió (con mes y días en que trabajó), jornales, bruto, descuentos, viáticos y neto, con los totales, por mes o de todos los meses, y botón para bajarlo en Excel. Sale de lo que se anota al bajar el Excel de serenos de cada barco (se reemplaza por barco al volver a bajarlo; el barco de prueba no anota). Cada renglón se puede quitar del resumen.

- **«Superó el tope» a mano**: casilla al lado del nombre de cada encargado en Administración → Encargados, por mes. Marcada, todos sus turnos de ese mes van sin O.S., jubilación ni ley (solo el aporte sindical), sin necesidad de cargar el tope; sirve cuando el sistema arranca con el mes empezado. En el Excel de encargados queda una nota («se marcó a mano que superó el tope»). Desmarcada, vuelve al cálculo automático con el tope del mes.
- **Paso 11**: tres botones: «Proforma final», «Liquidación de serenos» y «Liquidación de encargados».

- **Lanchas del Sur (paso 6)**: el **amarre** lleva servicio + lancha (dos lanchas si la eslora supera 150 m: servicio + 2 × 1070 en día hábil); el **desamarre NO lleva lanchas**: es solo el servicio de desamarre, con su recargo por día y hora.

## Doble seguridad en Serenos y Encargados

Para entrar a Administración → **Serenos** y **Encargados** (listas, resúmenes, topes y todas sus acciones) hay que tener permiso de Administración **y volver a poner la contraseña** (`/administracion/acceso-datos`). La contraseña habilita 20 minutos (cookie firmada, HttpOnly, atada al usuario y a su contraseña actual; se borra al salir). Cinco contraseñas mal seguidas bloquean 15 minutos. Después de vencida, la pantalla vuelve a pedirla y recuerda adónde se iba. El resto de Administración (proforma final, agencias, tarifas, fórmulas, calendario) no la pide. Los botones «Liquidación de serenos» y «Liquidación de encargados» del paso 11 no pasan por esta llave (son parte de armar la proforma).

## Mail a Aduana (salida aduanera)

En Nuestros barcos → Operados (agencias), cada barco con zarpada cargada tiene el botón **✉ Aduana** (con ⚠ si falta el destino): baja un `.eml` que Outlook abre como borrador. Asunto: `MV <BARCO> - SALIDA ADUANERA // SEA WHITE`. Para: mechegaray@, esuss@, alejarroyo@ e icostanzi@arca.gob.ar, con copia siempre a operations@seawhite.com.ar (`app/aduana.py`). El cuerpo lleva solo los cinco datos: Buque, Muelle (el terminal; el último si pasó por varios), Día y Hora de salida (`02/10/2026 – 21:01 hs`), Condición (CARGADO si cargó, EN LASTRE si descargó) y Destino. Lo que falte queda vacío para completarlo en el borrador.

- **RESULTADO, columna DIAS**: siempre 1 por renglón (un tramo de un sereno), por facturación, aunque haya trabajado ese tramo en dos o más días. Los jornales, los viáticos y los importes siguen sumando todos los días; el resumen de cada sereno sigue contando los jornales reales.

- **Dólar del fee (paso 2)**: campo opcional «Dólar para pasar el fee a pesos». Si se carga, el fee de la agencia (que está en USD) se pasa a pesos con ese dólar; todos los demás conceptos siguen con el dólar único del paso 1 (LAW también). Vacío = el mismo dólar del paso 1. En el Excel aparece «CAMBIO FEE» debajo del cambio común y el renglón del fee multiplica por esa celda; el total en USD no cambia. Se guarda con la proforma (se recupera al volver a cargarla).

- **BERTHING en el Head Tally**: el turno cuya actividad es BERTHING va en la proforma (Tally) pero **no se liquida** en el Excel de encargados: no sale en la declaración, no cuenta para los viáticos ni para el tope de aportes, y en el paso 8 no se pide encargado para ese turno. Si todos los turnos son BERTHING, avisa que no hay nada para liquidar.

- **AT ORDERS (turno especial del encargado)**: si la actividad de un turno de Head Tally es «AT ORDERS» (se escribe en la columna Actividad del paso 8; sugiere la lista), en la liquidación de encargados ese turno sale con un monto fijo, **$ 211.846,03**, todo como jornal básico (sin insalubridad ni producción), con sus descuentos y el tope de aportes como cualquier otro turno. El monto se cambia en Administración → Fórmulas («encargados_at_orders_ars»). La proforma no cambia: el turno sigue con su precio normal del Tally. Cuenta como día trabajado para los viáticos.

- **AT ORDERS, actualización**: el turno especial AT ORDERS es ahora un escalón propio del **Tally** (en la proforma y en la liquidación de encargados): vale un **monto fijo**, sin importar el día, la hora ni la categoría de la carga ($ 211.846,03 hoy = el jornal básico). El monto es una tarifa de Tally con su vigencia, en **Administración → Tarifas de Tally y Serenos** («Turno especial AT ORDERS»), para actualizarlo junto con los demás precios (no se calcula solo). En el Excel de la proforma aparece una fila «AT ORDERS» en la hoja TALLY solo si hubo turnos de ese tipo; en la liquidación de encargados va todo como jornal básico. Reemplaza al parámetro de Fórmulas de la versión anterior.

- **Actividad del turno de Head Tally**: en la pantalla de turnos del voucher (y en el paso 8 de la proforma final) la actividad se elige de una **lista desplegable** con BERTHING, LDG y AT ORDERS (también el turno extra). Si un turno viejo traía otra actividad, se conserva como una opción más. Cambiar un turno a AT ORDERS (o sacarlo) recalcula el precio al instante.

## Solapa FORMULAS del Excel de la proforma final (control interno)

- El Excel que se baja de la **proforma final** (no el de serenos ni el de encargados) trae una **cuarta solapa visible, «FORMULAS»**, después de la hoja de la agencia, SERENOS y TALLY (las hojas ocultas `_resumen` y `_estado` siguen al final). Sirve para que una persona prepare la proforma y otra la corrija: cada importe se sigue desde el dato hasta el número que figura en la hoja de la agencia.
- Estructura: **Datos generales** del buque y el dólar; un **bloque por renglón** en el mismo orden que la hoja de la agencia; **TOTAL y CONTROL**; los renglones **FOR YOUR ACCOUNT** (explicados, pero fuera del total); y las **reglas que se aplican** (dólar único y del fee, LAW, beneficio de muelle, LDS, tally, cargas sociales).
- Cada bloque dice **de dónde sale cada dato** («Paso N» = pantalla de la proforma final donde se carga o corrige, o la tabla/parámetro de Administración), la cuenta renglón por renglón y cierra con **IMPORTE EN LA PROFORMA** (verde) y su pasaje a la otra moneda con el dólar que corresponde (el del fee para el fee).
- Colores: **azul** = dato; **gris** = cuenta (**fórmula viva**: si se cambia un dato azul, se recalcula; llevan además el valor guardado para la Vista protegida); **verde** = importe de la proforma; **rojo** = algo que no coincide.
- **Importe modificado a mano**: si el importe que figura en la proforma no sale de la cuenta (se escribió a mano en su paso, o cambió un dato después), el bloque lo marca en rojo («ATENCIÓN…») con el importe de la proforma y la **diferencia** contra la cuenta. Una diferencia de un centavo es redondeo y no se marca.
- **CONTROL final**: suma de todos los renglones de la solapa contra el TOTAL de la hoja de la agencia (USD y ARS); dice «OK — todo coincide» o «REVISAR — no coincide».
- Cubre practicaje (UF, coeficientes, descuento, dos prácticos, service), muelle y fondeadero (días por bloques de 8 horas, beneficio de amarre fuera de día hábil, bloques no cobrados), vías navegables, LDS (amarre con lanchas, desamarre sin lanchas, escala, draft), tally (escalones, AT ORDERS fijo, cargas), serenos (grupos por tarifa, cargas, viáticos), migraciones/taxis/free pratique, aduana, importes fijos, renglones libres, fee y LAW (base = renglones en dólares, sin fee).
- Lo **omitido** («esto sí lo facturamos» destildado) no figura en ningún lado del Excel, tampoco en esta solapa. Sin dólar cargado la solapa avisa y no hace cuentas.
- Si por algún motivo la solapa no se puede armar, la proforma se baja igual (sin FORMULAS) y el error queda en el log. Código: `app/docgen/formulas_xlsx.py` (estilos y celdas) y `app/docgen/formulas_bloques.py` (los bloques).

## Historial de proformas (se guardan; abrir y modificar sin empezar de cero)

Antes el sistema no guardaba nada: la proforma vivía en el navegador y en el Excel (hoja oculta `_estado`). Como todos entran con clave, ahora **cada proforma queda guardada** (tabla `proformas_finales`): el estado completo, el buque, la agencia, el total (USD y ARS), **quién la hizo y cuándo**, quién la tocó por última vez y cuántas veces se modificó.

- **Cuándo se guarda**: al **descargar el Excel** de la proforma final (se guarda primero y después se baja), o con el botón **«💾 Guardar»** de la barra del asistente (sin descargar). El mensaje dice si quedó guardada; si no se pudo guardar, el Excel se baja igual y lo avisa en rojo.
- **Historial** (Administración → «Historial de proformas», o el botón «Historial» del asistente): arriba tres tarjetas de resumen (proformas guardadas, suma en USD, tocadas en los últimos 7 días) y debajo **una tarjeta por proforma** con el buque, la agencia, el total en USD (y en pesos), quién la hizo y quién la modificó (con avatar de color, «hace 12 min / hace 5 h / ayer 10:24» y, al pasar el mouse, la fecha exacta) y los botones Modificar y Excel. Las de **Husbandry** llevan una etiqueta y un borde naranja. Lista las últimas 500, con buscador por buque / agencia / persona y filtros **Todas / Mías / FULL-OPA / Husbandry**. Botón **Modificar** (la abre en el asistente con todo lo cargado; un cartel amarillo avisa que se está modificando esa proforma y quién la hizo) y botón **Excel** (vuelve a bajar el Excel de lo guardado, sin tocar el historial).
- **Modificar no crea otra**: al guardar o bajar el Excel de una proforma abierta del historial se actualiza ESA (suma una «modificación» y queda el nombre de quien la tocó y la fecha). «Cargar desde un Excel…» sigue existiendo y, al guardar, entra como una proforma nueva.
- **A prueba de pisarse**: si otra persona guardó la misma proforma mientras la tenías abierta, el sistema avisa («X guardó cambios en esta proforma el …») y pregunta si querés pisarla o no guardar. Y si se elige un barco que **ya tiene una proforma**, la pantalla muestra un aviso con el link para abrirla en vez de rehacerla (al guardar una nueva del mismo barco también avisa, y si se insiste, guarda otra).
- El **barco de prueba** nunca se guarda en el historial. Las proformas no se pueden borrar desde la pantalla (a propósito, para no perder historial por error).
- Lo guardado es el estado de la proforma; al re-descargar el Excel se vuelve a armar con las tarifas vigentes a la fecha del barco (las cargas sociales, el dólar y los importes cargados quedan como se guardaron).
- Código: `app/proformas_hist.py` (guardar / listar / conflictos), modelo `ProformaFinalReg`, rutas en `app/routers/proforma_final.py` (`/proforma-final/guardar`, `/proformas`, `/proformas/{id}/excel`), pantalla `administracion/proformas.html`.

## Tabla de mareas tentativa en el Line-up

En la fila de los botones del **Line-up Grain** (y del Flammable), pegado a la derecha, hay un cuadro de una sola línea, de la altura de un botón: «**Mareas** ‹ Hoy 28/10 › ▼ 01:26 1,26 ▲ 07:10 4,18 ▼ 13:57 0,77 ▲ 20:07 4,07». Muestra las pleamares y bajamares de **hoy y los dos días siguientes**, como un carrusel: las flechas ‹ › (o deslizar con el dedo) pasan de día a día. ▲ pleamar (azul) / ▼ bajamar (naranja), con la hora y la altura en metros. Al pasar el mouse dice que es una predicción tentativa del Servicio de Hidrografía Naval, en hora local, y que puede variar con el viento y la presión. Si no hay datos del día, el cuadro no se muestra. Se eligió esta ubicación (opción B de tres propuestas) porque **no agranda el encabezado** —el Line-up queda justo debajo de la barra de navegación— y porque la barra azul de arriba se va a ir cargando de más opciones. Si la fila no alcanza de ancho (pantallas de menos de unos 1300 px), el cuadro pasa a su propia fila, alineado a la derecha.

- **De dónde salen**: de las tablas de marea del SHN (`hidro.gov.ar/oceanografia/tmareas`), puerto **Puerto Ingeniero White** (código IWHI; referido al plano de reducción, nivel medio 2,74 m: por encima es pleamar). Ya viene cargado **todo 2026** (`app/data/mareas_iwhi_2026.json`, se siembra al arrancar) y se guarda en la tabla `mareas`.
- **No hace falta pasar ningún archivo ni actualizar cada 6 meses**: cuando falta un mes (por ejemplo al empezar 2027), el sistema lo consulta solo al SHN, a la misma página que se usaba a mano, y lo guarda. Si el SHN no responde, no se rompe nada (se muestra lo que haya y se reintenta como mucho una vez por hora). Para dejar un año cargado de antemano se puede generar el archivo `mareas_iwhi_AAAA.json` con la misma función `mareas.descargar`.
- Para sumar otro puerto (Rosales, Canal Principal a Bahía Blanca, etc.) alcanza con indicar su código del SHN; hoy está fijo en Ingeniero White.
- Código: `app/mareas.py`, ruta `/mareas/proximos` (`app/routers/mareas.py`) y el cuadro en `app/templates/lineup.html`.

## Confirmaciones del usuario (dólar del fee y tope de aportes)

- **Dólar del fee**: es un dólar especial que **se carga a mano** en cada proforma, en el campo «Dólar para pasar el fee a pesos» del paso 2. No hay una fuente automática ni una cotización fija: queda como está.
- **Tope de aportes del mes**: se **calcula en Administración fuera del sistema y después se carga a mano**, mes a mes, en Administración → Encargados (el sistema no lo calcula). Tiene que estar cargado antes de bajar el primer Excel de encargados del mes; el mes siguiente se vuelve a cargar.

## Tipo de servicio: FULL / OPA o HUSBANDRY

En **Nuestros barcos → Operados → Completar datos** hay un selector nuevo, **«Tipo de servicio»**, con dos opciones:

- **FULL / OPA** (por defecto): se proforma todo lo de siempre, según lo que se tilde en el voucher. Pide los mismos 5 datos de antes (amarre, comienzo, final, carga y zarpe).
- **HUSBANDRY**: solo gastos **básicos** (cambio de tripulación, embarco de provisiones, etc.). **No** se proforma nada de uso de muelle, fondeadero, vías navegables, practicaje, remolcadores, amarre/desamarre, escala, **encargado (head tally) ni serenos**. Como no hay operación de carga, el formulario solo pide **amarre y zarpe** (comienzo, final y carga se ocultan y no se guardan). Una estiba nunca es Husbandry.

Se guarda en el barco operado (`operated_vessels.servicio`, FULL o HUSBANDRY) y se copia a sus filas hermanas (las de las otras agencias del mismo movimiento). En la lista de operados, el barco Husbandry lleva la etiqueta **HUSBANDRY**.

**Qué cambia en cada lugar**
- **Voucher**: en Husbandry solo ofrece los conceptos básicos: *Agency expenses*, *Bank commission / LAW 25413*, *SENASA*, *Immigration*, *taxi de migraciones*, *Free pratique*, *taxi de sanidad* y *Custom overtime* **solo** con CLEARANCE, STORE LIST ENDORSED, FRESH WATER y PROVISIONS (sin ENTRANCE, LOADING, PERMANENCE ni BUNKERING). Quedan afuera port dues, channel toll, remolcadores, pilot, mooring, watchman, head tally y shore gangway (también en el formato Oceanway). Los conceptos agregados a mano siguen disponibles (ahí van, por ejemplo, el cambio de tripulación y las lanchas). **El documento que se descarga** (Excel o Word) también sale solo con los conceptos básicos: en Husbandry lo que no corresponde no se imprime aunque el voucher tuviera todo tildado (un voucher que antes era FULL, por ejemplo). La lista está en `app/docgen/voucher.py` (`HUSBANDRY_CLAVES`, `HUSBANDRY_CUSTOM`) y se cambia ahí.
- **Proforma final**: el paso 1 muestra el mismo selector (viene del barco elegido y se puede cambiar; sirve también para un barco escrito a mano). En Husbandry el asistente **salta los pasos 4, 5, 6, 8 y 9** (practicaje, muelle/fondeadero/vías, amarre/desamarre, tally, serenos) y queda 1, 2, 3, 7, 10 y 11; en el paso 3 solo pide amarre y zarpe. Todo lo que no corresponde se marca como omitido: no figura en la proforma, ni en el chequeo, ni en el Excel (que no trae las hojas SERENOS ni TALLY). El LAW NR 25413 se calcula solo sobre lo que sí figura. En el paso 11 se agregan los renglones libres (cambio de tripulación, provisiones, lanchas, etc.).
- El tipo de servicio viaja en el Excel y en el historial: al volver a cargar o abrir una proforma Husbandry, sigue siendo Husbandry.
- Un barco que ya tenía el voucher armado y se pasa a Husbandry (o al revés): el voucher sigue al barco; lo que no corresponde deja de salir.

## Aviso verde «voucher enviado, queda para proformar» (Administración)

Cuando alguien **envía el voucher** de un barco (ya tiene los datos completos y los conceptos elegidos, o sea que el barco está realmente listo), a las personas de **Administración** (y a los administradores) les aparece, debajo de la barra azul y en **cualquier pantalla**, un aviso verde: «✓ **PEPITO** envió el voucher del barco **MV X (agencia)** — queda para proformar» (con «(Husbandry)» si corresponde), con un botón **«Proformar →»** y una **×** para ocultarlo. (Primero se disparaba al completar los datos; se pasó al envío del voucher para que, cuando abren la proforma, los conceptos del voucher ya estén cargados. Completar los datos solo **no** avisa.)

- **Proformar →** abre el asistente de proforma final con ese barco ya elegido (con su agencia y su tipo de servicio).
- **Se actualiza solo** cada minuto (y al volver a la pestaña), sin recargar la página.
- **Desaparece** cuando la proforma de ese barco se guarda en el historial (al bajar el Excel o con «Guardar»).
- **Ocultar** es por persona: cada una oculta los suyos y no se los saca a las demás.
- Quien envió el voucher **no se avisa a sí misma**. Se muestran hasta 3 avisos juntos y un «y N más para proformar».
- Solo se avisa de los vouchers enviados **desde que se prendió la función** (los viejos no aparecen todos juntos). Hay un aviso por cada fila de agencia del barco (cada agencia se proforma aparte).
- Quien no es de Administración no ve nada. Código: `app/avisos.py`, ruta `/avisos/proformar` (`app/routers/avisos.py`), script en `app/static/nav.js` y estilo en `app/static/app.css`.

## Recuento de barcos operados: estiba sin tilde, barcos «sin clasificar» y alta a mano

Dos causas por las que un barco que se sacaba del line-up (la ✕) no figuraba en el recuento de Operados:

1. **Estiba sin el tilde «Nuestro»**: antes solo pasaban a Operados los barcos con «Nuestro» tildado. Ahora también pasa un barco que **tiene una estiba entre sus clientes** (principal u otras agencias), aunque no tenga el tilde. En ese caso cuentan **solo las estibas** (si el barco además tenía una agencia ajena, esa agencia no suma). Con el tilde, todo sigue como siempre: una fila por cada cliente. Un barco con estiba también aparece ahora en «En el line-up» de Nuestros barcos (y se anuncia), y se puede sacar desde ahí. «Lo cargué por error» sigue sin contar.
2. **Barcos «sin clasificar»** (por ejemplo del Flammable, como GAS VENUS): se archivaban bien, pero si no tenían cliente o su cliente no está en la planilla de Clientes **no aparecían en ninguna de las dos tablas** (Agencias / Estibas) y solo se nombraban en una nota. Ahora se muestran en una tabla aparte, **«Sin clasificar»**, con el selector para elegir el cliente (al elegirlo pasan a su tabla), y salen en una hoja «Sin clasificar» del Excel de operados.

**Para no perder barcos sin darse cuenta**: al eliminar un barco que **no** está tildado como «Nuestro», la pantalla avisa antes («no pasa a Operados ni cuenta en el recuento, salvo que tenga una estiba nuestra») y, después, dice si se contó («Eliminado: pasó a Operados») o no («Eliminado: NO se contó en Operados»).

**Corregir lo que ya se perdió**: en Nuestros barcos → Operados hay un botón **«+ Agregar a operados»**: se escribe el barco, se elige el cliente (agencia o estiba) y el mes, y queda en Operados para el recuento (no se duplica si ya está con ese cliente ese mes). Queda marcado como cargado a mano.
