FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Usuario sin privilegios dentro del contenedor
RUN useradd --create-home appuser
USER appuser
EXPOSE 8501
CMD ["streamlit", "run", "Inicio.py", "--server.address=0.0.0.0", "--server.port=8501", "--browser.gatherUsageStats=false"]
