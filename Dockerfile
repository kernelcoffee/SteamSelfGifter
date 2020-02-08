FROM python:3.7-alpine

# set version label
ARG BUILD_DATE
ARG VERSION
ARG RELEASE
LABEL build_version="version:- ${VERSION} Build-date:- ${BUILD_DATE}"

COPY steamselfgifter/ /app
COPY requirements/common.txt /app/requirements.txt

WORKDIR /app

RUN pip3 install -r requirements.txt

RUN mkdir /config
VOLUME /config

CMD [ "python3", "/app/steamselfgifter.py", "-c", "/config/config.ini"]
