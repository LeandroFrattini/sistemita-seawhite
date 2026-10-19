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

## Beneficio de fin de semana en Uso de muelle (confirmado por el usuario)

Solo afecta a **Uso de muelle** (vías navegables va por toneladas; el fondeo no se toca). Se calcula con el amarre y el **inicio de operación**.

- Si el barco amarra un **sábado, domingo o feriado DESPUÉS de las 21:00** (21:01 en adelante; a las 21:00 en punto no) y **no empieza a operar ese mismo día**,
  no se cobra el tercio 16–24 de ese día ni los días siguientes que sean sábado, domingo o feriado, hasta el día en que arranca la operación.
- El día en que arranca la operación se cobra **entero desde las 00:00** (según la salida). También se cobra todo día hábil con el barco ya amarrado sin operar.
- Amarre antes de las 21:00, o un día hábil (aunque después sea fin de semana): se cobra todo. Los **días no laborables no cuentan**; solo feriados del Calendario.
- Se aplica de forma **sugerida**: sale tildada la casilla cuando se detecta el caso y se puede destildar (el barco a veces hace otras operaciones).
- En el Excel queda la nota «beneficio de fin de semana: X días no cobrados» y la foto en el estado (`sin_beneficio`, `perdonados`).
- Ejemplo: amarra sáb 17/10 21:30, opera lun 19/10 08:30, zarpa mar 20/10 10:00 → se perdonan 1,33 días (0,33 del sábado + 1,00 del domingo).
- Asumido (a confirmar): la misma regla de las 21:00 vale cuando el amarre es domingo o feriado.

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

## «Esto sí lo facturamos» destildado = no figura en ningún lado (ronda 16)

- Al **destildar «Esto sí lo facturamos»**, ese punto **no figura en ningún lado de la proforma**: ni en el cuerpo, ni en FOR YOUR ACCOUNT, ni en el total, ni en la base de LAW; si es el Tally o los Serenos, **tampoco lleva su hoja** (TALLY / SERENOS) en el Excel.
- Si se prefiere que figure al pie, al destildar aparece una elección: **«No figura en la proforma»** (por defecto) o **«Figura al pie, por cuenta del armador (FOR YOUR ACCOUNT)»**.
- Estado: `omitido` (no figura) y `cuenta_ajena` (al pie) en cada concepto, nunca las dos (si llegan las dos, manda «al pie»).
- En el **chequeo general** cada renglón tiene un desplegable (Se factura / Al pie / No figura) y, abajo, una lista plegable **«No figuran en esta proforma»** para volver a incluirlos.
- Lo que no figura no se pide como pendiente en los pasos (por ejemplo, si el practicaje no figura no se exigen sus datos) y no aparece en el resumen.
