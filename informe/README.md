# Informe

- `arquitectura_costos.html`: fuente del informe (se puede abrir directo en el navegador).
- `Informe_Kiosco_Escolar_Saludable.pdf`: versión para entregar, generada desde el HTML.
- `capturas/`: capturas de pantalla de la app que muestra el informe (ver su README).

## Regenerar el PDF

Después de editar el HTML o agregar capturas, desde la raíz del repo:

```
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu \
  --no-pdf-header-footer \
  --print-to-pdf="$PWD/informe/Informe_Kiosco_Escolar_Saludable.pdf" \
  "file://$PWD/informe/arquitectura_costos.html"
```

En Windows o Linux, cambiar la ruta al ejecutable de Chrome. También sirve abrir el HTML en
Chrome y usar Imprimir > Guardar como PDF (sin encabezados ni pies de página).
