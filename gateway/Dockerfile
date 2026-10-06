FROM python:3.10-slim

WORKDIR /app

RUN pip install grpcio grpcio-tools PyJWT

COPY gateway.py storage_pb2.py storage_pb2_grpc.py ./
COPY certs/ ./certs/

EXPOSE 50051

CMD [ "python", "gateway.py" ]