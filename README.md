# En modo seguro — Portal de noticias del mercado asegurador

Proyecto en dos partes:

- **La fachada** (`index.html`): la web que ven los usuarios. Diseño limpio,
  tech y ejecutivo. Al abrir, lee `noticias.json` y muestra las noticias.
- **El motor** (`actualizar_noticias.py`): un programa que corre una vez por
  día, junta las novedades del seguro y reescribe `noticias.json`.

```
actualizar_noticias.py  ──escribe──▶  noticias.json  ──lee──▶  index.html
```

## Archivos

| Archivo | Qué es |
|---|---|
| `index.html` | La web (fachada). |
| `actualizar_noticias.py` | El motor que junta las noticias. |
| `noticias.json` | Las noticias que muestra la web (lo genera el motor). |
| `requirements.txt` | Las librerías que necesita el motor. |

## Probarlo en tu compu

1. Instalá las dependencias (una sola vez):
   ```bash
   pip install -r requirements.txt
   ```
2. Corré el motor para generar `noticias.json`:
   ```bash
   python actualizar_noticias.py
   ```
3. Levantá la web con un servidor local (para que pueda leer el JSON):
   ```bash
   python -m http.server 8000
   ```
   Y entrá a `http://localhost:8000`.

> Si abrís `index.html` haciendo doble clic (sin servidor), el navegador
> bloquea la lectura del JSON: en ese caso la web muestra noticias de
> respaldo. Sirviéndola con un servidor (o hosteada), lee el JSON real.

## Dejarlo automático (1 vez por día)

### Opción A — GitHub Actions + GitHub Pages (gratis, recomendada)
Subís el proyecto a un repo de GitHub y agregás este archivo en
`.github/workflows/actualizar.yml`:

```yaml
name: Actualizar noticias
on:
  schedule:
    - cron: '0 9 * * *'   # todos los días 09:00 UTC (~06:00 ARG)
  workflow_dispatch:       # permite correrlo a mano
jobs:
  actualizar:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -r requirements.txt
      - run: python actualizar_noticias.py
      - run: |
          git config user.name "noticias-bot"
          git config user.email "bot@users.noreply.github.com"
          git add noticias.json
          git commit -m "Actualiza noticias" || echo "sin cambios"
          git push
```
Después activás **GitHub Pages** en el repo para publicar `index.html`.
El Action regenera `noticias.json` cada día y la web queda al día sola.

### Opción B — Servidor con cron (Linux)
```bash
crontab -e
# agregá esta línea (corre 09:00 todos los días):
0 9 * * * cd /ruta/al/proyecto && /usr/bin/python3 actualizar_noticias.py
```

### Opción C — Windows (Programador de tareas)
Crear una tarea básica → diaria → acción “Iniciar programa”:
`python` con argumento `actualizar_noticias.py` y “Iniciar en” la carpeta del proyecto.

## Agregar más fuentes

- **Portales con RSS**: agregalos en la lista `FEEDS_RSS` del motor
  (en WordPress el feed suele ser `<dominio>/feed/`).
- **SSN / SRT (scraping)**: hay ejemplos comentados en `PAGINAS_HTML`.
  Hay que poner la URL del listado de noticias y ajustar los selectores.

## Notas honestas

- Los **feeds RSS** son la fuente confiable y ya cubren buena parte de las
  resoluciones de la SSN y la SRT (porque los medios del sector las publican).
- El **scraping directo** de organismos es frágil: si cambian el HTML, hay que
  retocar los selectores.
- El **Boletín Oficial** carga con JavaScript; integrarlo bien requiere usar su
  API. Es un paso aparte que se puede sumar más adelante.
