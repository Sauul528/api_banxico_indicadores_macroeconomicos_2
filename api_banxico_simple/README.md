# API Indicadores Macroeconómicos (Banxico)

API hecha con FastAPI que consume el SIE de Banxico (dólar, UDI y un metal)
y devuelve históricos y proyecciones a 30, 60 y 90 días.
Validación con Pydantic y documentación automática con Swagger.

## Cómo correrla
1. `python -m venv .venv` y activarlo (`.venv\Scripts\activate` en Windows)
2. `pip install -r requirements.txt`
3. Copiar `.env.example` como `.env` y llenar el token y la serie del metal
4. `uvicorn main:app --reload`
5. Abrir http://127.0.0.1:8000/docs

## Endpoints
- `GET /{indicador}/historico?dias=30`
- `GET /{indicador}/proyeccion/{30|60|90}`

`{indicador}` puede ser `dolar`, `udi` o `metal`.

## Método de proyección
Regresión lineal sobre el último año de datos: se calcula la línea de tendencia
y se prolonga 30, 60 o 90 días. 
