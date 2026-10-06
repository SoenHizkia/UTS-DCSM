import grpc
import storage_pb2
import storage_pb2_grpc
from concurrent import futures
import hashlib
import json
import os
import sys

def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()

class StorageServicer(storage_pb2_grpc.StorageServicer):
    def __init__(self, mode, node_dir, backup_stub=None):
        self.mode = mode
        self.node_dir = node_dir
        self.backup_stub = backup_stub
        os.makedirs(f"{self.node_dir}/objects", exist_ok=True)
        self.meta_file = f"{self.node_dir}/metadata.json"

    def _save_metadata(self, file_id, meta):
        metadata = {}
        if os.path.exists(self.meta_file):
            with open(self.meta_file, "r") as f:
                metadata = json.load(f)
        metadata[file_id] = meta
        
        # Atomic write (menulis ke temporari lalu di-rename)
        temp_file = self.meta_file + ".tmp"
        with open(temp_file, "w") as f:
            json.dump(metadata, f)
        os.replace(temp_file, self.meta_file)

    def Store(self, request, context):
        if self.mode != "primary":
            return storage_pb2.OperationReply(success=False, message="Write only allowed on Primary")

        # 1. Validasi Hash SHA-256
        if sha256_bytes(request.content) != request.sha256:
            return storage_pb2.OperationReply(success=False, message="INTEGRITY_FAIL: Checksum mismatch")

        # 2. Replikasi sinkron ke Backup
        if self.backup_stub:
            try:
                rep_res = self.backup_stub.Replicate(request)
                if not rep_res.success:
                    return storage_pb2.OperationReply(success=False, message="Replication to Backup failed")
            except grpc.RpcError:
                return storage_pb2.OperationReply(success=False, message="Backup Offline - Upload Aborted")

        # 3. Simpan file lokal
        filepath = f"{self.node_dir}/objects/{request.file_id}.bin"
        with open(filepath, "wb") as f:
            f.write(request.content)
            
        self._save_metadata(request.file_id, {
            "filename": request.filename,
            "security_label": request.security_label,
            "sha256": request.sha256
        })

        return storage_pb2.OperationReply(success=True, message="File Stored and Replicated", file_id=request.file_id)

    def Replicate(self, request, context):
        # Menyimpan payload replikasi dari Primary
        filepath = f"{self.node_dir}/objects/{request.file_id}.bin"
        with open(filepath, "wb") as f:
            f.write(request.content)
        self._save_metadata(request.file_id, {
            "filename": request.filename,
            "security_label": request.security_label,
            "sha256": request.sha256
        })
        return storage_pb2.OperationReply(success=True, message="Replicated ACK")

    def Fetch(self, request, context):
        if not os.path.exists(self.meta_file):
            return storage_pb2.DownloadReply(success=False, message="File not found")
            
        with open(self.meta_file, "r") as f:
            metadata = json.load(f)
            
        if request.file_id not in metadata:
            return storage_pb2.DownloadReply(success=False, message="File not found")

        meta = metadata[request.file_id]
        filepath = f"{self.node_dir}/objects/{request.file_id}.bin"
        
        with open(filepath, "rb") as f:
            content = f.read()

        # Validasi hash sebelum mengirim ke klien
        if sha256_bytes(content) != meta["sha256"]:
            return storage_pb2.DownloadReply(success=False, message="CORRUPT DATA: Data on disk tampered")

        return storage_pb2.DownloadReply(
            success=True,
            filename=meta["filename"],
            security_label=meta["security_label"],
            content=content,
            sha256=meta["sha256"]
        )

def serve(mode):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    if mode == "primary":
        backup_channel = grpc.insecure_channel('backup_storage:50053')
        stub = storage_pb2_grpc.StorageStub(backup_channel)
        servicer = StorageServicer("primary", "primary_data", stub)
        server.add_insecure_port('[::]:50052')
        print("Primary Storage berjalan di port 50052...")
    else:
        servicer = StorageServicer("backup", "backup_data")
        server.add_insecure_port('[::]:50053')
        print("Backup Storage berjalan di port 50053...")

    storage_pb2_grpc.add_StorageServicer_to_server(servicer, server)
    server.start()
    server.wait_for_termination()

if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else "primary"
    serve(mode)