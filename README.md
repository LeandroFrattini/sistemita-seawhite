# Sistemita SeaWhiters

App interna del equipo de Operaciones (carpeta del proyecto: `lineup`). Arrancó
como el line-up de las terminales de Bahía Blanca (Grain y Flammable), export
a Excel, reportes por barco a cada cliente y "Barcos (ID)" con reportes
operativos (Berthing / Commenced Loading / Loading Shifts / Sailed) — y va a
seguir sumando funciones del día a día del equipo.

## Correr

```
run.bat
```

Crea el virtualenv la primera vez, instala dependencias y levanta el server en
<http://localhost:8010>. En la red interna: `http://IP-DE-LA-PC:8010`.

Usuario inicial: **admin / admin** (cambialo en Admin → Usuarios, o por `.env`).

## Cómo se usa

1. **Line-up**: cargás fecha, y por terminal agregás barcos. El orden de las
   filas = fila de espera del muelle.
   - `Nuestro` se marca solo si LOCAL = "Sea White" (se puede forzar a mano).
   - `PRINCIPAL`: escribí el nombre; si coincide con un cliente cargado queda
     vinculado (verde) y le llega el reporte.
   - `Otras agencias`: otros clientes a los que también hay que mandarles el
     mail (hasta los que quieras).
   - **↻ Recalcular ETB/ETC**: del primer barco de cada terminal se respeta lo
     cargado; para los siguientes `ETB = ETC del anterior` (o la ETA si es
     posterior) y `ETC = ETB + días de carga de ese barco`.
2. **Reportes**: muestra un mail por barco propio × cliente. Botón `.eml`
   (se abre en Outlook como borrador listo para enviar) o `Copiar cuerpo`.
   `Descargar todos` baja un zip con todos los `.eml`.
3. **Exportar**: Excel interno (con LOCAL/PRINCIPAL/Otras agencias) y Excel para
   clientes (sin esas columnas). Botón para archivar una copia con fecha.
4. **Clientes**: nombre (= lo que va en PRINCIPAL), TO del mail, mails, y formato
   (Excel / WBL).
5. **Admin**: usuarios y terminales (código = encabezado del Excel/mail; muelle =
   rótulo que usa el texto WBL).

## Stack

FastAPI + SQLite + Jinja2 + openpyxl. Base de datos en `data/lineup.db`.

## Seguridad

- **Login:** bloqueo temporal tras 5 fallos por usuario (25 por IP) en 15 min; mensaje
  idéntico para usuario inexistente o clave incorrecta. Contraseñas nuevas: mínimo 10
  caracteres, sin usuario adentro ni claves comunes.
- **Sesión:** cookie firmada, `HttpOnly`, `SameSite=Lax` y `Secure` por HTTPS. Vence a los 30
  días en el servidor. Cambiar la contraseña cierra las demás sesiones de esa cuenta.
- **Verificación en dos pasos (TOTP):** Google/Microsoft Authenticator o Authy. Es
  **obligatoria** para quien tenga Admin, Admin PDA o Administración; opcional para el resto
  (`/seguridad`). Cada activación entrega 8 códigos de recuperación de un solo uso. Si alguien
  pierde el celular: Admin → Usuarios → **Reiniciar 2FA**.
  El secreto se guarda cifrado con una clave derivada de `SECRET_KEY`: **si se cambia
  `SECRET_KEY`, todos tienen que volver a activar el 2FA** (y se cierran todas las sesiones).
- **HTTP:** sin `/docs` ni `/openapi.json`; cabeceras CSP, HSTS, X-Frame-Options, nosniff;
  rechazo de POST desde otro origen; `Cache-Control: no-store` en las páginas con datos.
- Eventos de seguridad (login fallido/bloqueado, 2FA, cambios de clave) van al log
  (logger `seguridad`), visible en el panel de Render.

### Pruebas

```
pip install -r requirements-dev.txt
python -m pytest tests
```
