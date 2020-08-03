FROM python:3-alpine

ENV CONFLUENCE_USERNAME=""
ENV CONFLUENCE_PASSWORD=""
ENV CONFLUENCE_API_URL=""
ENV CONFLUENCE_SPACE=""
ENV CONFLUENCE_ANCESTOR_ID=""

WORKDIR /usr/src/app

COPY . .

RUN apk add --no-cache git \
    && pip install --no-cache-dir -r requirements.txt

CMD [ "python", "./markdown-to-confluence.py" ]