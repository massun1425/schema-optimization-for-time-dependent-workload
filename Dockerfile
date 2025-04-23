FROM postgres:latest

RUN mkdir -p /home/root/data

COPY ./data/ /home/root/data/

WORKDIR /home/root

RUN mkdir -p mv-query-optimization

COPY ./ ./mv-query-optimization/

COPY ./gurobi.lic /opt/gurobi/gurobi.lic

# install useful commands
RUN apt-get update
RUN apt-get install -y python3
RUN apt install -y python3-pip
RUN pip3 install --no-cache-dir -r ./mv-query-optimization/requirements.txt --break-system-packages
RUN apt install -y python-is-python3

# setup sql server data
RUN psql -U postgres data/setup.sql

ENV POSTGRES_PASSWORD=pass
