FROM python:3.11-slim

WORKDIR /app

COPY requirements_webapp.txt .
RUN pip install --no-cache-dir -r requirements_webapp.txt

COPY . .

EXPOSE 8080

CMD ["python", "lemon_squeeze_webapp.py"]
