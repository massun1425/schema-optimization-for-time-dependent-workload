FROM postgres:latest

# PostgreSQLの環境変数設定
ENV POSTGRES_PASSWORD=pass
ENV POSTGRES_DB=imdbload

# 必要なディレクトリ作成
RUN mkdir -p /home/root/data

# データコピー
COPY ./data/ /home/root/data/

# 作業ディレクトリ設定
WORKDIR /home/root

# Python環境セットアップ
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python-is-python3 \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Pythonパッケージインストール（Gurobi以外）
RUN pip3 install --no-cache-dir \
    matplotlib==3.10.1 \
    networkx==3.4.2 \
    numpy==2.2.4 \
    pandas==2.2.3 \
    pyautogui==0.9.54 \
    regex==2024.11.6 \
    sqlparse==0.5.3 \
    prettytable==3.15.1 \
    duckdb==1.2.1 \
    psycopg2-binary \
    --break-system-packages

# PostgreSQL拡張機能インストール
RUN apt-get update && apt-get install -y \
    postgresql-contrib \
    && rm -rf /var/lib/apt/lists/*

# pg_ivmソースインストール
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    postgresql-server-dev-18 \
    && git clone https://github.com/sraoss/pg_ivm.git \
    && cd pg_ivm \
    && make \
    && make install \
    && cd .. \
    && rm -rf pg_ivm \
    && apt-get remove -y git build-essential postgresql-server-dev-18 \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Pythonパッケージインストール（Gurobi以外）
RUN pip3 install --no-cache-dir \
    matplotlib==3.10.1 \
    networkx==3.4.2 \
    numpy==2.2.4 \
    pandas==2.2.3 \
    pyautogui==0.9.54 \
    regex==2024.11.6 \
    sqlparse==0.5.3 \
    prettytable==3.15.1 \
    duckdb==1.2.1 \
    psycopg2-binary \
    --break-system-packages

# プロジェクトファイルコピー
RUN mkdir -p mv-query-optimization
COPY ./ ./mv-query-optimization/

# Gurobi Optimizerインストール
RUN wget -q https://packages.gurobi.com/12.0/gurobi12.0.1_linux64.tar.gz && \
    tar -xzf gurobi12.0.1_linux64.tar.gz && \
    mv gurobi1201 /opt/gurobi && \
    rm gurobi12.0.1_linux64.tar.gz

# Gurobi環境変数設定
ENV GUROBI_HOME=/opt/gurobi
ENV PATH=$PATH:/opt/gurobi/bin
ENV LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/opt/gurobi/lib
ENV GRB_LICENSE_FILE=/opt/gurobi/gurobi.lic

# Gurobi Pythonインターフェースインストール
RUN pip3 install --no-cache-dir gurobipy==12.0.1 --break-system-packages

# PostgreSQL初期化後に実行するスクリプト
COPY ./data/setup.sql /docker-entrypoint-initdb.d/

# 権限設定
RUN chmod +x /home/root/mv-query-optimization/data/setup.sh
