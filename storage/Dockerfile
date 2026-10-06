FROM python:3.10-slim

WORKDIR /app

RUN pip install grpcio grpcio-tools

COPY storage_node.py storage_pb2.py storage_pb2_grpc.py ./

# Biar bisa passing parameter primary ataupun backup
ENTRYPOINT [ "python", "storage_node.py"]