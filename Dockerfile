# syntax=docker/dockerfile:1
# Author: hugofnm
# Description: UniceAPI Dockerfile

FROM python

ADD /src /src

WORKDIR /src

RUN pip3 install -r requirements.txt

EXPOSE 5000

CMD ["python3", "run.py"]