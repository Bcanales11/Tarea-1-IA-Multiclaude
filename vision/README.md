# Visión - Kiosco Escolar Saludable

Cumple el requisito: "modelo de Visión computacional 100% local" con "lógica adicional"
(no es aplicar un modelo pre-entrenado tal cual). Acá la lógica adicional son 3 capas, igual
que el ejemplo del profesor (celular dentro del bounding box de la cabeza), pero con una capa
extra:

1. **Detección** (YOLOv8 reentrenado con fotos propias): 1 sola clase, `sello`.
2. **Agrupamiento en "productos"**: no hay clase `producto` entrenada. Los `sello` detectados
   se agrupan por cercanía relativa a su propio tamaño (`vision_utils.agrupar_sellos_en_productos`):
   sellos muy cercanos entre sí se asumen del mismo producto; sellos lejanos, de productos
   distintos. Esto cumple el mismo objetivo que tener una clase `producto` (no mezclar sellos de
   dos productos que aparecen juntos en la misma foto) sin necesitar entrenarla.
3. **OCR + clasificación**: cada sello se recorta y se le pasa EasyOCR (100% local, sin API)
   para leer el texto ("ALTO EN AZÚCARES", etc.) y clasificarlo en uno de los 4 nutrientes
   críticos.
4. **Regla de negocio**: basta **un solo** sello para que el producto no sea apto — esto no es
   una suposición, se verificó explícitamente contra el RAG en `../rag/resultados_con_sin_rag.csv`
   (el art. 110 bis usa "o", no "y", entre los 4 nutrientes).

**Limitación conocida**: como no hay clase `producto`, un producto SIN sellos (apto) no genera
ninguna detección — el sistema solo "ve" algo cuando hay al menos un sello. Para la demo, un
producto apto simplemente no muestra ningún recuadro en pantalla (a diferencia de uno no apto,
que sí). Es un trade-off aceptado: "nada detectado" se interpreta como "vendible".

## Por qué YOLO propio + OCR, y no varias clases ("sello_azucar", "sello_sodio", "producto", etc.)

Con pocas fotos (~100-150 por persona), es más robusto entrenar UNA sola clase "sello" — el
octágono negro es el objeto más fácil de detectar que existe (alto contraste, forma fija) — y
dejar que el OCR (que ya viene entrenado en millones de imágenes de texto) lea cuál nutriente
dice. Entrenar clases visualmente casi idénticas (mismo octágono, solo cambia el texto) con
pocos ejemplos por clase habría dado un modelo menos confiable. Por la misma razón se descartó
entrenar una clase `producto`: a diferencia del sello, cada producto tiene forma, color y
textura distintos entre sí — sin un patrón visual consistente, ~400 fotos no alcanzan para que
YOLO generalice bien esa clase. De ahí el agrupamiento geométrico del paso 2 en vez de detección.

## Paso a paso

### 1. Tomar las fotos
Copia tus fotos a `dataset/images_sin_etiquetar/`. Recomendado (idea original del grupo):
- ~80-150 fotos de productos reales (despensa/supermercado).
- Mezcla: productos con 0, 1, 2, 3 y 4 sellos "ALTO EN" visibles.
- Varía ángulo, distancia, luz y fondo — así el modelo generaliza a la cámara real del kiosco.
- Incluye algunas fotos con MÁS DE UN producto en el cuadro (para que la lógica de traslape
  tenga sentido: si no, sobra con "todos los sellos son del único producto").

### 2. Etiquetar
Dos opciones, según cómo lo esté haciendo el grupo:

**Opción A — local con OpenCV** (un compañero, sin conexión):
```
python3 etiquetar.py
```
Dibuja con el mouse la(s) caja(s) de cada sello visible en la foto (ver instrucciones en
pantalla). Sin herramientas externas, solo OpenCV.

**Opción B — Roboflow** (etiquetado colaborativo en la nube, ver detalles de configuración
más abajo en "Notas de colaboración"): una vez descargado el export en formato YOLOv8,
```
python3 importar_roboflow.py "ruta/a/la/carpeta/exportada"
```
Copia las imágenes a `dataset/images/{train,val}` y convierte los labels (incluso si vienen
como polígono en vez de caja) al formato que usa este proyecto — con esto puedes saltarte el
paso 3 y entrenar directo.

### 3. Separar train/val
Solo si etiquetaste con la Opción A (con Roboflow ya viene separado):
```
python3 dividir_dataset.py
```

### 4. Entrenar
```
python3 entrenar_yolo.py --epocas 60
```
Usa el GPU integrado (Metal/MPS) del Apple M3 automáticamente si está disponible; si no, cae a
CPU. Con ~100 fotos y YOLOv8n esto debería tardar pocos minutos en este equipo.

### 5. Probar
```
python3 deteccion_kiosco.py --imagen dataset/images/val/alguna_foto.jpg   # una foto
python3 deteccion_kiosco.py                                                # cámara en vivo
```
Dibuja las cajas, muestra APTO/NO APTO y en consola imprime el detalle (nutrientes detectados
y el motivo, listo para conectarlo después con el LLM/RAG en la interfaz final).

## Notas para el informe de arquitectura

- **GPU mínima**: entrenamiento e inferencia corren en el GPU integrado Apple M3 (Metal/MPS) de
  este equipo; en un PC sin GPU dedicado, YOLOv8n también corre en CPU (más lento, pero viable
  para un solo kiosco). Para escalar a varias cámaras concurrentes sí conviene GPU dedicado —
  esto se detalla en el informe de escalabilidad (pendiente).
- Pesos entrenados quedan en `modelos/kiosco_saludable/weights/best.pt`.
