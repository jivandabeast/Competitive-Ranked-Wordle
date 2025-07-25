FROM python:3.12.3-alpine
WORKDIR /wordle
COPY ./adaptive_card.json /wordle/adaptive_card.json
COPY ./requirements.txt /wordle/requirements.txt
RUN pip3 install --no-cache-dir --upgrade -r requirements.txt
COPY ./app.py /wordle/app.py
CMD ["fastapi", "run", "app.py", "--proxy-headers", "--port", "80"]
