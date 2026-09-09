# Cómo dejarlo andando para las 10 personas

La app es un **servidor web**: corre en **una sola máquina** y los demás entran
desde el navegador. No hay que instalar nada en las otras PC.

## 1. Elegir la "PC-servidor"

Cualquier PC de la oficina que **quede prendida** durante el horario de trabajo.
Ideal: una que no se apague ni suspenda (podés desactivar la suspensión en
Configuración → Sistema → Energía). Si no hay una dedicada, puede ser la de
Leandro mientras esté prendida.

## 2. Instalar (una vez, en esa PC)

1. Copiar la carpeta `lineup` a esa PC (ej. `C:\lineup`).
2. Tener **Python** instalado (python.org, tildar "Add to PATH").
3. Clic derecho en **`instalar-inicio.bat`** → **Ejecutar como administrador**.
   - Prepara el entorno y crea una tarea de Windows que arranca la app **sola,
     sin ventana**, cada vez que se inicia sesión en esa PC.
4. Arrancarla ahora sin reiniciar: abrir una consola y correr
   `schtasks /run /tn "Lineup Sea White"`  (o reiniciar la PC).

## 3. Averiguar la dirección

En la PC-servidor, abrir consola y escribir `ipconfig`. Anotar la
**Dirección IPv4** (ej. `192.168.1.50`).

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
