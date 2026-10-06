# Secure Distributed File Storage System

Proyek ini adalah implementasi sistem penyimpanan file terdistribusi berbasis *microservices* untuk memenuhi evaluasi Ujian Tengah Semester (UTS) mata kuliah Distributed Computing Security Model (DCSM). 

Sistem ini dikembangkan menggunakan Python gRPC dan dilengkapi dengan jaminan keamanan transport (mTLS), otorisasi akses (RBAC/Bell-LaPadula), integritas file (SHA-256), serta replikasi *Primary-Backup*.

## Arsitektur Sistem

Arsitektur terdiri dari 4 komponen utama yang saling berinteraksi:

1. **Client (`client.py`)**: Bertugas melakukan *upload* dan *download* file. Menggunakan sertifikat lokal untuk autentikasi mTLS dan JWT (JSON Web Token) untuk mengirimkan label keamanan user (PUBLIC/CONFIDENTIAL/SECRET).
2. **API Gateway (`gateway.py`)**: Bertindak sebagai pintu masuk (*entry point*). Memvalidasi sertifikat mTLS dan JWT, mencatat *Audit Log* (ALLOW/DENY), menegakkan aturan Bell-LaPadula (No Read Up), serta mengarahkan *request* ke *Storage Node*.
3. **Primary Storage (`storage_node.py`)**: Menyimpan data di dalam lokal volume secara *persistence*, memvalidasi integritas file dengan *hash* SHA-256, dan mereplikasi data secara sinkron ke *Backup Storage*.
4. **Backup Storage (`storage_node.py`)**: Berjalan dalam mode *backup*. Menerima replikasi dari *Primary* dan menjadi tujuan *fallback* (pengganti) apabila *Primary Node* sedang *offline*.

Infrastruktur dideploy menggunakan **Docker Swarm** dengan mode *overlay network* agar masing-masing *service* terisolasi dan berkomunikasi secara internal.

---

## Cara Menjalankan (Deployment)

Proyek ini dapat di-deploy secara instan ke dalam Docker Swarm menggunakan file `docker-compose.yaml`.

```bash
# Inisiasi swarm (jika belum)
docker swarm init

# Berikan label pada node (sesuaikan nama node)
docker node update --label-add role=primary <nama-node-vm-2>
docker node update --label-add role=backup <nama-node-vm-3>

# Deploy stack
docker stack deploy -c docker-compose.yaml dcsm_stack
```

# ==========================================
# TC-01: Upload file otentik oleh user berwenang
# ==========================================
# 1. Buat file teks kecil untuk pengujian[cite: 6]
echo "Ini adalah file test TC-01" > file_tc01.txt

# 2. Upload file ke sistem (Otomatis masuk Primary & replikasi ke Backup)[cite: 1, 3]
python client.py upload file_tc01.txt --doc_label PUBLIC --user alice --user_label PUBLIC

# ==========================================
# TC-02: Akses file bertingkat (Bell-LaPadula violation)
# ==========================================
# 1. Buat file dokumen sangat rahasia[cite: 6]
echo "Ini dokumen sangat rahasia" > file_rahasia.txt

# 2. Upload file dengan label SECRET oleh user SECRET[cite: 1]
# -> CATAT UUID/FILE_ID YANG MUNCUL DI TERMINAL!
python client.py upload file_rahasia.txt --doc_label SECRET --user admin --user_label SECRET

# 3. Coba download dengan user PUBLIC (Ganti <FILE_ID_RAHASIA> dengan UUID dari langkah 2)[cite: 1, 2]
python client.py download <FILE_ID_RAHASIA> --user bob --user_label PUBLIC

# ==========================================
# TC-03: Pengujian Integritas File (SHA-256)
# ==========================================
# 1. Upload file pengujian integritas[cite: 6]
echo "File tes integritas" > file_integritas.txt
python client.py upload file_integritas.txt --doc_label PUBLIC --user alice --user_label PUBLIC

# 2. LANGKAH MANUAL: Buka VM 2 (Primary Node)[cite: 4]
# Masuk ke direktori volume primary_data/objects/ dan ubah secara paksa isi file bin tersebut[cite: 3]
# Contoh: echo "data dirusak" > /var/lib/docker/volumes/dcsm_stack_primary_data/_data/objects/<FILE_ID>.bin

# 3. Coba download kembali file yang sudah dirusak tersebut (Ganti <FILE_ID_INTEGRITAS>)[cite: 1, 3]
python client.py download <FILE_ID_INTEGRITAS> --user alice --user_label PUBLIC

# ==========================================
# TC-04: Uji Keamanan mTLS
# ==========================================
# 1. Ubah nama sertifikat klien agar tidak terbaca / tidak valid[cite: 1, 6]
mv certs/client.crt certs/client.crt.backup

# 2. Coba jalankan upload, koneksi harusnya ditolak oleh Gateway[cite: 2]
python client.py upload file_tc01.txt --doc_label PUBLIC --user alice --user_label PUBLIC

# 3. Kembalikan nama sertifikat seperti semula agar bisa lanjut tes[cite: 1]
mv certs/client.crt.backup certs/client.crt

# ==========================================
# TC-05: Node Failover / Backup Sync
# ==========================================
# 1. Buat dan upload file baru saat Primary masih hidup[cite: 1, 6]
echo "File untuk tes failover" > file_failover.txt
python client.py upload file_failover.txt --doc_label PUBLIC --user alice --user_label PUBLIC

# 2. Matikan Primary Storage di Docker Swarm (Jalankan di VM 1 / Manager)[cite: 4]
docker service scale dcsm_stack_primary_storage=0

# 3. Tunggu jeda jaringan Docker Swarm (15 detik), lalu lakukan download (Ganti <FILE_ID_FAILOVER>)[cite: 1, 2]
sleep 15
python client.py download <FILE_ID_FAILOVER> --user alice --user_label PUBLIC

# 4. Kembalikan Primary Storage ke kondisi semula[cite: 4]
docker service scale dcsm_stack_primary_storage=1

# ==========================================
# TC-06: Automated Deployment Test
# ==========================================
# 1. Bersihkan environment sebelumnya[cite: 6, 7]
docker stack rm dcsm_stack
sleep 10 # Tunggu hingga container benar-benar terhapus

# 2. Deploy ulang seluruh arsitektur secara otomatis[cite: 4, 6]
docker stack deploy -c docker-compose.yaml dcsm_stack

# 3. Cek status deployment, harus mencapai replicas 1/1 dalam < 3 menit[cite: 4, 6]
docker service ls
