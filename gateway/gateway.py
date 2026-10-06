import grpc
import storage_pb2
import storage_pb2_grpc
import jwt
from concurrent import futures
import json
from datetime import datetime
import os

# Konfigurasi Dummy JWT Secret & Aturan
JWT_SECRET = "rahasia_super_aman"
LEVEL = {"PUBLIC": 0, "CONFIDENTIAL": 1, "SECRET": 2}

def can_read(user_label, file_label):
    # Bell-LaPadula: No Read Up
    return LEVEL.get(user_label, 0) >= LEVEL.get(file_label, 0)

def write_audit(action, user, file_id, decision, reason):
    log = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "user": user,
        "action": action,
        "file_id": file_id,
        "decision": decision,
        "reason": reason
    }
    with open("gateway-audit.jsonl", "a") as f:
        f.write(json.dumps(log) + "\n")
    print(f"AUDIT: {log}")

class FileGatewayServicer(storage_pb2_grpc.FileGatewayServicer):
    def __init__(self, primary_channel, backup_channel):
        self.primary_stub = storage_pb2_grpc.StorageStub(primary_channel)
        self.backup_stub = storage_pb2_grpc.StorageStub(backup_channel)

    def _verify_jwt(self, token):
        try:
            return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def Upload(self, request, context):
        payload = self._verify_jwt(request.jwt)
        if not payload:
            write_audit("UPLOAD", "unknown", request.file_id, "DENY", "invalid_jwt")
            return storage_pb2.OperationReply(success=False, message="JWT Invalid/Expired")
        
        user_id = payload.get("sub")
        
        # Teruskan ke Primary Storage
        try:
            response = self.primary_stub.Store(request)
            write_audit("UPLOAD", user_id, request.file_id, "ALLOW" if response.success else "DENY", response.message)
            return response
        except grpc.RpcError as e:
            write_audit("UPLOAD", user_id, request.file_id, "DENY", "primary_storage_offline")
            return storage_pb2.OperationReply(success=False, message="Primary Storage Unavailable")

    def Download(self, request, context):
        payload = self._verify_jwt(request.jwt)
        if not payload:
            return storage_pb2.DownloadReply(success=False, message="JWT Invalid/Expired")

        user_label = payload.get("label", "PUBLIC")
        user_id = payload.get("sub")

        # Coba ambil dari Primary dulu
        try:
            response = self.primary_stub.Fetch(request, timeout=3)
            source = "primary"
        except grpc.RpcError:
            # TC-05: Read Fallback ke Backup saat Primary Offline
            try:
                response = self.backup_stub.Fetch(request)
                source = "backup"
            except grpc.RpcError:
                return storage_pb2.DownloadReply(success=False, message="All Storages Offline")

        if not response.success:
            return response

        # Evaluasi Bell-LaPadula
        if not can_read(user_label, response.security_label):
            write_audit("DOWNLOAD", user_id, request.file_id, "DENY", "bell_lapadula_no_read_up")
            return storage_pb2.DownloadReply(success=False, message="Permission Denied: Clearance level too low")

        write_audit("DOWNLOAD", user_id, request.file_id, "ALLOW", f"source_{source}")
        return response

def serve():
    # Setup mTLS untuk Server
    key_path = os.environ.get('TLS_KEY', 'certs/server.key')
    crt_path = os.environ.get('TLS_CERT', 'certs/server.crt')
    ca_path = os.environ.get('TLS_CA', 'certs/ca.crt')
    
    with open('certs/server.key', 'rb') as f: server_key = f.read()
    with open('certs/server.crt', 'rb') as f: server_cert = f.read()
    with open('certs/ca.crt', 'rb') as f: ca_cert = f.read()
    
    server_credentials = grpc.ssl_server_credentials(
        [(server_key, server_cert)],
        root_certificates=ca_cert,
        require_client_auth=True # Wajib mTLS
    )

    primary_channel = grpc.insecure_channel('primary_storage:50052')
    backup_channel = grpc.insecure_channel('backup_storage:50053')

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    storage_pb2_grpc.add_FileGatewayServicer_to_server(FileGatewayServicer(primary_channel, backup_channel), server)
    
    server.add_secure_port('[::]:50051', server_credentials)
    print("Gateway berjalan di port 50051 dengan mTLS...")
    server.start()
    server.wait_for_termination()

if __name__ == '__main__':
    serve()