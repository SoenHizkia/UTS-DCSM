# Secure Distributed File Storage System

Proyek ini adalah implementasi sistem penyimpanan file terdistribusi berbasis *microservices* untuk memenuhi evaluasi Ujian Tengah Semester (UTS) mata kuliah Distributed Computing Security Model (DCSM). 

Sistem ini dikembangkan menggunakan Python gRPC dan dilengkapi dengan jaminan keamanan transport (mTLS), otorisasi akses (RBAC/Bell-LaPadula), integritas file (SHA-256), serta replikasi *Primary-Backup*.

## Arsitektur Sistem

Arsitektur terdiri dari 4 komponen utama yang saling berinteraksi secara aman di dalam jaringan Docker Swarm:

1. **Client (`client.py`)**: Bertugas melakukan permintaan *upload* dan *download* file. Klien menggunakan sertifikat lokal untuk autentikasi mTLS dan menyertakan JWT (JSON Web Token) yang berisi label keamanan pengguna (PUBLIC, CONFIDENTIAL, atau SECRET).
2. **API Gateway (`gateway.py`)**: Berfungsi sebagai pintu masuk utama. Gateway memvalidasi sertifikat mTLS dan JWT klien, mencatat setiap aktivitas ke dalam *Audit Log* (ALLOW/DENY), menegakkan aturan Bell-LaPadula (*No Read Up*), serta merutekan *request* ke *Storage Node* yang tepat.
3. **Primary Storage (`storage_node.py`)**: Node penyimpanan utama yang menyimpan data di dalam volume lokal secara persisten. Node ini juga memvalidasi *hash* SHA-256 untuk menjamin integritas file, serta secara otomatis mereplikasi data secara sinkron ke *Backup Storage*.
4. **Backup Storage (`storage_node.py`)**: Berjalan dalam mode siaga (*backup*). Menyimpan salinan data dari *Primary* dan otomatis melayani klien sebagai *fallback* apabila *Primary Node* mengalami gangguan atau *offline*.

---

## Skenario Pengujian (Test Cases)

Berikut adalah perintah operasional untuk memvalidasi pemenuhan Test Case (TC-01 hingga TC-06). Anda dapat menyalin baris perintah di bawah ini secara berurutan.

### TC-01: Upload File Otentik
**Tujuan:** Memastikan upload sah berhasil disimpan di Primary, tereplikasi ke Backup, dan tercatat "ALLOW" di Audit Log Gateway.
```bash
echo "Ini adalah file test TC-01" > file_tc01.txt

python client.py upload file_tc01.txt --doc_label PUBLIC --user alice --user_label PUBLIC
```
### TC-02: Pelanggaran Akses (Bell-LaPadula Violation)
**Tujuan:** Memastikan aturan No Read Up berjalan. User dengan label Public akan ditolak saat membaca dokumen Secret.
```bash
echo "Ini dokumen sangat rahasia" > file_rahasia.txt

# 1. Upload dokumen sebagai SECRET (CATAT UUID/FILE_ID DARI HASIL PERINTAH INI)
python client.py upload file_rahasia.txt --doc_label SECRET --user admin --user_label SECRET

# 2. Coba download menggunakan user tingkat PUBLIC (Ganti <FILE_ID> dengan UUID di atas)
python client.py download <FILE_ID> --user bob --user_label PUBLIC
```
### TC-03: Pengujian Integritas File (SHA-256)
**Tujuan:** Mendeteksi perubahan file ilegal (tampering) langsung di media penyimpanan.
```bash
echo "File tes integritas" > file_integritas.txt

# 1. Upload file normal (CATAT UUID/FILE_ID)
python client.py upload file_integritas.txt --doc_label PUBLIC --user alice --user_label PUBLIC

# 2. LAKUKAN MANUAL: Masuk ke VM 2 (Primary), buka direktori volume primary_data/objects/
# dan edit isi file <FILE_ID>.bin menggunakan teks editor. Simpan perubahan.

# 3. Coba download file yang telah dirusak tersebut
python client.py download <FILE_ID> --user alice --user_label PUBLIC
```
### TC-04: Uji Keamanan mTLS
**Tujuan:** Memastikan koneksi tanpa sertifikat klien yang sah akan ditolak oleh sistem.
```bash
# 1. Ubah nama sertifikat klien agar terbaca tidak valid
mv certs/client.crt certs/client.crt.backup

# 2. Eksekusi upload (Koneksi akan langsung ditolak/error di tahap SSL Handshake)
python client.py upload file_tc01.txt --doc_label PUBLIC --user alice --user_label PUBLIC

# 3. Kembalikan nama sertifikat seperti semula
mv certs/client.crt.backup certs/client.crt
```
### TC-05: Node Failover / Backup Sync
**Tujuan:** Memastikan ketersediaan layanan (fault tolerance). Saat Primary offline, klien tetap dapat mengunduh file dari Backup.
```bash
echo "File tes failover" > file_failover.txt

# 1. Upload file saat sistem berjalan normal (CATAT UUID/FILE_ID)
python client.py upload file_failover.txt --doc_label PUBLIC --user alice --user_label PUBLIC

# 2. Matikan Primary Storage (Jalankan perintah ini di Node Manager Swarm)
docker service scale dcsm_stack_primary_storage=0

# 3. Tunggu 10-15 detik, lalu coba unduh (Akan tercatat source_backup di Gateway log)
python client.py download <FILE_ID> --user alice --user_label PUBLIC

# 4. Kembalikan Primary Storage untuk operasional normal
docker service scale dcsm_stack_primary_storage=1
```
### TC-06: Automated Deployment Test
**Tujuan:** Memastikan seluruh sistem dan container dapat diluncurkan secara otomatis dan siap dalam waktu kurang dari 3 menit.
```bash
# 1. Hapus stack environment sebelumnya (jika ada)
docker stack rm dcsm_stack

# 2. Deploy ulang seluruh arsitektur menggunakan compose
docker stack deploy -c docker-compose.yaml dcsm_stack

# 3. Cek status container, pastikan kolom REPLICAS menjadi 1/1
docker service ls
```
