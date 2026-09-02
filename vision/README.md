# Visión - Kiosco Escolar Saludable

Cumple el requisito: "modelo de Visión computacional 100% local" con "lógica adicional"
(no es aplicar un modelo pre-entrenado tal cual). Acá la lógica adicional son 3 capas, igual
que el ejemplo del profesor (celular dentro del bounding box de la cabeza), pero con una capa
extra:

1. **Detección** (YOLOv8 reentrenado con fotos propias): 2 clases, `producto` y `sello`.
2. **Traslape**: por cada `producto` detectado, se buscan los `sello` cuya área cae dentro de
   su bounding box (`vision_utils.sello_esta_dentro_de_producto`) — evita contar sellos de
   OTRO producto que esté al lado en la misma foto.
3. **OCR + clasificación**: cada sello contenido se recorta y se le pasa EasyOCR (100% local,
   sin API) para leer el texto ("ALTO EN AZÚCARES", etc.) y clasificarlo en uno de los 4
   nutrientes críticos.
4. **Regla de negocio**: basta **un solo** sello para que el producto no sea apto — esto no es
   una suposición, se verificó explícitamente contra el RAG en `../rag/resultados_con_sin_rag.csv`
   (el art. 110 bis usa "o", no "y", entre los 4 nutrientes).

## Por qué YOLO propio + OCR, y no 4 clases "sello_azucar", "sello_sodio", etc.

Con pocas fotos (~100-150), es más robusto entrenar UNA sola clase "sello" — el octágono negro
es el objeto más fácil de detectar que existe (alto contraste, forma fija) — y dejar que el OCR
(que ya viene entrenado en millones de imágenes de texto) lea cuál nutriente dice. Entrenar 4
clases visualmente casi idénticas (misma forma, mismo color, solo cambia el texto) con pocos
ejemplos por clase habría dado un modelo mucho menos confiable.

## Paso a paso

### 1. Tomar las fotos
Copia tus fotos a `dataset/images_sin_etiquetar/`. Recomendado (idea original del grupo):
- ~80-150 fotos de productos reales (despensa/supermercado).
- Mezcla: productos con 0, 1, 2, 3 y 4 sellos "ALTO EN" visibles.
- Varía ángulo, distancia, luz y fondo — así el modelo generaliza a la cámara real del kiosco.
- Incluye algunas fotos con MÁS DE UN producto en el cuadro (para que la lógica de traslape
  tenga sentido: si no, sobra con "todos los sellos son del único producto").

### 2. Etiquetar
```
python3 etiquetar.py
```
Dibuja con el mouse la caja del producto y luego la(s) caja(s) de cada sello visible en esa foto
(ver instrucciones en pantalla). Sin herramientas externas, solo OpenCV.

### 3. Separar train/val
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
