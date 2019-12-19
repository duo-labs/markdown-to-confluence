FROM python:3-alpine

WORKDIR /usr/src/app

RUN apk add --no-cache git

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD [ "python", "./markdown-to-confluence.py" ]