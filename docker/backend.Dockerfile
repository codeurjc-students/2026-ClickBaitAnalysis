FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    HF_HOME=/modelos

# 1 · Dependencias del lockfile.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2 · torch en su rueda de CPU, y sentence-transformers. Fuera del lockfile,
#     así que con versiones fijadas a lo medido. Va antes que los modelos
#     porque cambia mucho menos.
RUN pip install --no-cache-dir torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir sentence-transformers==5.6.0

# 3 · Modelos. Sólo las fichas: la capa se rehace cuando cambia model_cards.py,
#     aunque sólo cambie un texto y ningún modelo.
COPY backend/__init__.py backend/
COPY backend/integrations/__init__.py backend/integrations/
COPY backend/integrations/nlp/__init__.py \
     backend/integrations/nlp/model_cards.py \
     backend/integrations/nlp/outputs.py \
     backend/integrations/nlp/
COPY docker/hornear_modelos.py /tmp/
RUN python /tmp/hornear_modelos.py && rm /tmp/hornear_modelos.py

# 4 · El código, lo último porque es lo que más cambia.
COPY backend/ backend/

# Sin red hacia HuggingFace: lo que no se horneó da error en vez de descargarse.
ENV HF_HUB_OFFLINE=1

EXPOSE 8000

CMD ["uvicorn", "backend.api.app:app", "--host", "0.0.0.0", "--port", "8000"]