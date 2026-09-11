# Ayudante "Lineup Mailer"

Hace que el botón **"Abrir en Outlook"** de la pantalla Reportes abra el mail
**directamente en Outlook**, con la **firma normal de cada uno** al final y sin
tocar ninguna configuración.

## Para los usuarios: instalar la versión .exe (recomendado)

**No hace falta Python.** Desde la app → **Reportes**, hay un link
**"⬇ Descargar ayudante de Outlook"** (o entrá directo a
`/static/downloads/ayudante-outlook.zip` en el navegador). Descomprimir y
doble clic en `instalar-helper.bat` — eso es todo. Ver `paquete-src/LEEME.md`
para el detalle.

## Para desarrollo: correr desde el código fuente (Python)

Esta carpeta (`helper/`) es el código fuente de `lineup_mailer.py`, usado
para compilar el `.exe` (`construir-exe.bat`). También se puede correr
directo con Python, sin compilar:

1. Esa PC tiene que tener **Outlook de escritorio** y **Python** instalados.
2. Copiar esta carpeta `helper` a la PC.
3. Doble clic en **`instalar-helper.bat`**.
4. Verificar: abrir el navegador en <http://127.0.0.1:8765/ping> — tiene que
   responder `{"ok": true, ...}`.

Queda corriendo en segundo plano (sin ventana) y arranca solo al prender la PC.

## Recompilar el .exe

Con el `.venv` de esta carpeta armado (pywin32 instalado), correr
**`construir-exe.bat`** — compila `lineup_mailer.exe` y arma de nuevo
`app/static/downloads/ayudante-outlook.zip` con los `.bat` de
`paquete-src/`.

## Uso

En la app → **Reportes** → botón **"Abrir en Outlook"** de cada barco.
Se abre la ventana de Outlook con el mail listo (destinatarios, asunto, cuerpo
y tu firma). Revisás y **Enviar**.

Si el botón dice que no encuentra el ayudante, es que no está corriendo:
correr `instalar-helper.bat` de nuevo, o `schtasks /run /tn "Lineup Mailer"`.

El botón **`.eml`** sigue estando como alternativa por si alguna PC no tiene el
ayudante.

## Actualizar el ayudante

Si te pasan una versión nueva de `lineup_mailer.py`: copiar el archivo y volver
a correr `instalar-helper.bat` (frena el viejo y arranca el nuevo).

## Frenar / desinstalar

- Frenar ahora: `detener-helper.bat`
- Desinstalar del inicio: `schtasks /delete /tn "Lineup Mailer" /f`
