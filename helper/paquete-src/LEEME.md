# Ayudante "Lineup Mailer"

Hace que el botón **"✉ Abrir en Outlook"** de la app abra el mail directo en
**tu** Outlook, con tu firma normal, sin instalar Python ni nada raro.

## Instalar (una vez, en cada PC que vaya a mandar reportes)

1. Esta PC necesita **Outlook de escritorio** instalado.
2. Descomprimí esta carpeta en un lugar **fijo** (por ejemplo
   `C:\LineupMailer\`) -- **no la dejes en Descargas** ni en una carpeta
   temporal. El acceso directo de inicio apunta para acá: si después movés
   o borrás la carpeta, el ayudante deja de arrancar solo.
3. Doble clic en **`instalar-helper.bat`** (no hace falta admin).
4. Confirmar: abrir el navegador en **http://127.0.0.1:8765/ping** — tiene
   que responder `{"ok": true, ...}`.

Con eso el ayudante queda corriendo en segundo plano (sin ventana) y arranca
solo cada vez que se inicia sesión en esa PC.

### Si deja de arrancar solo después de reiniciar la PC

Lo más probable es que el antivirus (Windows Defender u otro) haya puesto
en cuarentena o borrado `lineup_mailer.exe` -- es un .exe sin firma digital
y algunos antivirus lo marcan como sospechoso. Revisá el historial de
protección / cuarentena de Windows Defender; si aparece ahí, agregá esta
carpeta como excepción y volvé a correr `instalar-helper.bat`.

## Uso

En la app → **Reportes** → botón **"✉ Abrir en Outlook"** (o "Abrir
seleccionados en Outlook" para varios de una). Se abre la ventana de Outlook
con el mail listo — revisás y **Enviás** vos.

Si el botón dice que no encuentra el ayudante: volvé a correr
`instalar-helper.bat`.

## Frenar / desinstalar

- Frenar ahora: doble clic en **`detener-helper.bat`**.
- Sacarlo del inicio: borrar el acceso directo `LineupMailer.lnk` de la
  carpeta Inicio de Windows (`Win+R` → escribir `shell:startup` → Enter).
