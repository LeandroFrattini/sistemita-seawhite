# Ayudante "Lineup Mailer"

Hace que el botón **"✉ Abrir en Outlook"** de la app abra el mail directo en
**tu** Outlook, con tu firma normal, sin instalar Python ni nada raro.

## Instalar (una vez, en cada PC que vaya a mandar reportes)

1. Esta PC necesita **Outlook de escritorio** instalado.
2. Doble clic en **`instalar-helper.bat`** (no hace falta admin).
3. Confirmar: abrir el navegador en **http://127.0.0.1:8765/ping** — tiene
   que responder `{"ok": true, ...}`.

Con eso el ayudante queda corriendo en segundo plano (sin ventana) y arranca
solo cada vez que se inicia sesión en esa PC.

## Uso

En la app → **Reportes** → botón **"✉ Abrir en Outlook"** (o "Abrir
seleccionados en Outlook" para varios de una). Se abre la ventana de Outlook
con el mail listo — revisás y **Enviás** vos.

Si el botón dice que no encuentra el ayudante: volvé a correr
`instalar-helper.bat`.

## Frenar / desinstalar

- Frenar ahora: doble clic en **`detener-helper.bat`**.
- Sacarlo del inicio: borrar el archivo `LineupMailer.exe` de la carpeta
  Inicio de Windows (`Win+R` → escribir `shell:startup` → Enter).
