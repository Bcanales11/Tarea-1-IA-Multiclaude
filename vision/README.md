# Visión: detección de sellos "ALTO EN"

Modelo de visión 100% local con lógica adicional sobre la detección:

1. **Detección**: YOLOv8n reentrenado con nuestras fotos, una sola clase (`sello`).
2. **Agrupamiento en productos**: no entrenamos una clase `producto`. Los sellos detectados
   se agrupan por cercanía relativa a su propio tamaño (`vision_utils.agrupar_sellos_en_productos`).
   Sellos muy cercanos se asumen del mismo producto; sellos lejanos, de productos distintos.
3. **OCR y clasificación**: cada sello se recorta y se le pasa EasyOCR (local) para leer el
   texto ("ALTO EN AZÚCARES", etc.) y clasificarlo en uno de los 4 nutrientes.
4. **Regla de negocio**: basta un solo sello para que el producto no sea apto (art. 110 bis del
   Decreto 13/2015, que usa "o" entre los nutrientes).

**Limitación**: como no hay clase `producto`, un producto sin sellos no genera ninguna
detección. En la demo, un producto apto simplemente no muestra recuadro.

## Por qué una sola clase y OCR

Con pocas fotos es más robusto entrenar una clase "sello" (octágono negro, alto contraste,
forma fija) y dejar que el OCR lea qué nutriente dice. Entrenar clases casi idénticas
visualmente (mismo octágono, solo cambia el texto) con pocos ejemplos por clase habría dado
un modelo menos confiable. Tampoco entrenamos `producto` porque cada producto tiene forma,
color y textura distintos y con nuestras fotos no habría generalizado bien.

## Paso a paso

### 1. Fotos
Copiar las fotos a `dataset/images_sin_etiquetar/`. Conviene mezclar productos con 0, 1, 2,
3 y 4 sellos, variar ángulo, distancia, luz y fondo, e incluir algunas fotos con más de un
producto en el cuadro.

### 2. Etiquetar
Dos opciones:

**Opción A, local con OpenCV:**
```
python3 etiquetar.py
```
Se dibujan con el mouse las cajas de cada sello visible (instrucciones en pantalla).

**Opción B, Roboflow** (etiquetado colaborativo, es la que usamos al final). Una vez
descargado el export en formato YOLOv8:
```
python3 importar_roboflow.py "ruta/a/la/carpeta/exportada"
```
Copia las imágenes a `dataset/images/{train,val}` y convierte los labels (también si vienen
como polígono) al formato de cajas. Con esto se puede saltar el paso 3.

### 3. Separar train/val
Solo si se etiquetó con la Opción A:
```
python3 dividir_dataset.py
```

### 4. Entrenar
```
python3 entrenar_yolo.py --epocas 60
```
Usa el GPU integrado (Metal/MPS) de Apple Silicon si está disponible; si no, CPU.

### 5. Probar
```
python3 deteccion_kiosco.py --imagen dataset/images/val/alguna_foto.jpg   # una foto
python3 deteccion_kiosco.py                                                # cámara en vivo
```
Dibuja las cajas, muestra APTO / NO APTO y en consola imprime los nutrientes detectados y el
motivo.

## Notas

- Los pesos entrenados quedan en `modelos/kiosco_saludable/weights/best.pt`. Ese archivo lo
  usan `deteccion_kiosco.py` y `app/server.py`.
- Sin GPU dedicada, YOLOv8n también corre en CPU (más lento, pero viable para un kiosco).
