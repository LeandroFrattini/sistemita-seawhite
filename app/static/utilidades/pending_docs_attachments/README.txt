Plantillas fijas para el mail de "Pending Docs" (Operaciones > Utilidades).

Subir aca los siguientes archivos, con estos nombres exactos, para que
salgan adjuntos de verdad en el .eml generado (ver ATTACHMENT_FILES en
app/routers/operaciones.py):

- maritime_health_declaration.doc
- ballast_water_reporting_form.doc
- senasa_form_a.pdf
- senasa_form_b.pdf
- om_1645.pdf
- om_1646.pdf
- om_1647.pdf
- om_1648.pdf
- shore_pass.xls

Si un archivo no esta, ese adjunto simplemente se omite -- el mail sale
igual, solo sin ese adjunto puntual.
