FROM python:3.8.12-slim-buster
MAINTAINER Josef Nevrly <jnevrly@alps.cz>

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE 1
# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED 1

# Install Poetry
RUN apt-get update && apt-get -y install curl
RUN curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py | python -
ENV PATH="/root/.poetry/bin:${PATH}"

# Install the source
WORKDIR /usr/src/app
COPY . ./
RUN poetry config virtualenvs.create false && poetry install --no-dev --no-interaction --no-ansi

WORKDIR /app
ENTRYPOINT ["byroapi"]
