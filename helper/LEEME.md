# Ayudante "Lineup Mailer"

Hace que el botón **"Abrir en Outlook"** de la pantalla Reportes abra el mail
**directamente en Outlook**, con la **firma normal de cada uno** al final y sin
tocar ninguna configuración.

## Instalación (una vez por PC que mande reportes)

1. Esa PC tiene que tener **Outlook de escritorio** y **Python** instalados.
2. Copiar esta carpeta `helper` a la PC.
3. Doble clic en **`instalar-helper.bat`**.
4. Verificar: abrir el navegador en <http://127.0.0.1:8765/ping> — tiene que
   responder `{"ok": true, ...}`.

Queda corriendo en segundo plano (sin ventana) y arranca solo al prender la PC.

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
