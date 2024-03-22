FROM python:3.10-slim

COPY app/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY /app /app
RUN mkdir data
WORKDIR /app



ENTRYPOINT ["/app/main.py"] # allows for passing args