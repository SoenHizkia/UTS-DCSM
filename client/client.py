import grpc
import storage_pb2
import storage_pb2_grpc
import argparse
import hashlib
import jwt
import os
from datetime import datetime, timedelta
import uuid

JWT_SECRET = "rahasia_super_aman"

def generate_test_jwt(username, label):
    payload = {
        "sub": username,
        "label": label,
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def sha256_file(filepath):
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def get_secure_channel():
    with open('certs/client.key', 'rb') as f: client_key = f.read()
    with open('certs/client.crt', 'rb') as f: client_cert = f.read()
    with open('certs/ca.crt', 'rb') as f: ca_cert = f.read()
    
    # mTLS Client Authentication
    credentials = grpc.ssl_channel_credentials(
        root_certificates=ca_cert,
        private_key=client_key,
        certificate_chain=client_cert
    )
    
    options = (('grpc.ssl_target_name_override', 'SERVER-BARU'),)
    
    return grpc.secure_channel('192.168.67.101:50051', credentials, options=options)

def upload_file(args):
    filepath = args.file_path
    if not os.path.exists(filepath):
        print(f"File {filepath} tidak ditemukan!")
        return

    filename = os.path.basename(filepath)
    file_id = str(uuid.uuid4())
    token = generate_test_jwt(args.user, args.user_label)
    
    with open(filepath, "rb") as f:
        content = f.read()

    request = storage_pb2.UploadRequest(
        file_id=file_id,
        filename=filename,
        security_label=args.doc_label,
        content=content,
        sha256=sha256_file(filepath),
        jwt=token
    )

    with get_secure_channel() as channel:
        stub = storage_pb2_grpc.FileGatewayStub(channel)
        response = stub.Upload(request)
        print(f"[{response.success}] {response.message} (ID: {file_id})")

def download_file(args):
    token = generate_test_jwt(args.user, args.user_label)
    request = storage_pb2.DownloadRequest(file_id=args.file_id, jwt=token)

    with get_secure_channel() as channel:
        stub = storage_pb2_grpc.FileGatewayStub(channel)
        response = stub.Download(request)
        if response.success:
            save_path = f"downloaded_{response.filename}"
            with open(save_path, "wb") as f:
                f.write(response.content)
            print(f"SUKSES: Download berhasil! Disimpan di {save_path}")
            print(f"Label Keamanan Dokumen: {response.security_label}")
        else:
            print(f"GAGAL: {response.message}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Klien Secure Distributed Storage")
    subparsers = parser.add_subparsers(dest="command")

    # Upload command
    upload_parser = subparsers.add_parser("upload", help="Upload sembarang file lokal")
    upload_parser.add_argument("file_path", help="Path lengkap file di sistem komputer Anda")
    upload_parser.add_argument("--doc_label", choices=["PUBLIC", "CONFIDENTIAL", "SECRET"], default="PUBLIC", help="Label untuk file")
    upload_parser.add_argument("--user", default="alice", help="Username pengunggah")
    upload_parser.add_argument("--user_label", choices=["PUBLIC", "CONFIDENTIAL", "SECRET"], default="PUBLIC", help="Tingkat izin user")

    # Download command
    download_parser = subparsers.add_parser("download", help="Download file menggunakan file_id")
    download_parser.add_argument("file_id", help="ID UUID file")
    download_parser.add_argument("--user", default="bob", help="Username pengunduh")
    download_parser.add_argument("--user_label", choices=["PUBLIC", "CONFIDENTIAL", "SECRET"], default="PUBLIC", help="Tingkat izin user pengunduh")

    args = parser.parse_args()
    if args.command == "upload":
        upload_file(args)
    elif args.command == "download":
        download_file(args)