# Cómo dejarlo andando para las 10 personas

La app es un **servidor web**: corre en **una sola máquina** y los demás entran
desde el navegador. No hay que instalar nada en las otras PC.

## 1. Elegir la "PC-servidor"

Cualquier PC de la oficina que **quede prendida** durante el horario de trabajo.
Ideal: una que no se apague ni suspenda (podés desactivar la suspensión en
Configuración → Sistema → Energía). Si no hay una dedicada, puede ser la de
Leandro mientras esté prendida.

## 2. Pasar la carpeta a esa PC

1. En tu PC, copiá la carpeta **`C:\proyectos\lineup`** entera a un pendrive o
   carpeta de red, y pegала en la PC-servidor (ej. `C:\lineup`).
   - Incluí la subcarpeta **`data\`** (ahí está todo lo cargado: usuarios,
     clientes, line-ups Grain y Flammable).
   - **Borrá la carpeta `.venv`** en la copia (se rearma sola; la vieja no sirve
     en otra PC).
2. En la PC-servidor, instalá **Python** (python.org → tildar *"Add Python to PATH"*).

## 3. Instalar (una vez)

### Si tenés admin en esa PC
Clic derecho en **`instalar-inicio.bat`** → **Ejecutar como administrador**.
Hace todo: entorno, **abre el puerto 8010 en el firewall**, deja la app
arrancando sola y sin ventana al iniciar sesión, la arranca, y te muestra la IP.

### Si NO tenés admin en esa PC
Doble clic normal en **`instalar-inicio-sin-admin.bat`**. Hace todo lo mismo
**menos el firewall**. Al final te dice si pudo abrir el puerto o no.

Si no pudo, el **único** paso que necesita admin es abrir el puerto **una vez**.
Pedile a alguien de IT que corra en una consola (como admin):

```
netsh advfirewall firewall add rule name="Lineup Sea White 8010" dir=in action=allow protocol=TCP localport=8010
```

Hasta que eso pase, en esa PC la app ya funciona (`http://localhost:8010`), pero
las otras PC no pueden entrar.

> Si la PC se reinicia y **nadie inicia sesión**, la app no arranca hasta que
> alguien entre.

> Si el firewall es un problema imposible: se puede poner la app en un servidor
> en la nube (VPS) — entran de cualquier lado con el login, sin depender de una
> PC prendida. Avisá y lo vemos.

## 4. Los demás entran

Cada uno abre el navegador en:  **http://192.168.1.50:8010**
(reemplazar por la IP real). Conviene que se lo guarden en favoritos.

Todos ven y editan **el mismo line-up** en tiempo real. Cada uno entra con su
usuario (los das de alta vos en **Admin**).

## Manejo del día a día

- **Actualizar a una versión nueva**: reemplazar los archivos de la carpeta y
  correr `detener.bat` y después `schtasks /run /tn "Lineup Sea White"`.
- **Frenarla**: `detener.bat`.
- **Ver que esté viva**: entrar a `http://IP:8010` desde cualquier PC.
- **Backup**: copiar el archivo `data\lineup.db` (ahí está todo).

## Reportes / Outlook

Recomendado: instalar el **ayudante** en cada PC que mande reportes (carpeta
`helper`, ver `helper/LEEME.md`). Con eso, el botón **"Abrir en Outlook"** abre
el mail directo en Outlook con la **firma normal de esa persona** al final, sin
tocar ninguna configuración.

Sin el ayudante, queda el botón **`.eml`** como alternativa (descarga el mail y
se abre en Outlook; en ese caso Outlook puede agregar su firma automática).
