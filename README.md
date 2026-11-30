# Matchanee

Sebuah **Progressive Web App (PWA)** untuk mengurangi separuh pekerjaan klik matching di MatchaPro.

---

## Masalah yang Diselesaikan

Kamu harus klik 2x untuk setiap perlakuan SBR di MatchaPro, kan? Dengan ini, kamu cukup klik 1x. That's it. That's all.

---

## Cara Menjalankan

1. Pastikan Python 3 sudah terpasang.
2. Pasang dependensi:
   - **Otomatis (Windows)**: Jalankan `requirements.bat` (skrip satu kali pakai yang memasang dependensi lalu menghapus dirinya sendiri).
   - **Manual**: `pip install flask requests jinja2` (jika skrip di atas sudah terhapus).
3. Jalankan server aplikasi:
   ```bash
   python server.py
   ```
4. Akses melalui peramban:
   - **Perangkat Lokal**: `http://localhost:5000`
   - **Jaringan Wi-Fi/Tablet**: `http://<IP_KOMPUTER>:5000`
5. Login pake akun yang dikasih pusat. kode kegiatan:
   - **36**: Matching baru
   - **35**: Matching false
   - Atau masukkan angka yang tampil di URL setelah "kegiatan/" ketika kamu masuk ke menu matching. Lihat gambar berikut.
   ![Kode Matching](kodematching.png) 
6. Kamu bisa mencet shortcut huruf berikut untuk matching:
   - [Enter]: Match
   - [U]: Unmatch
   - [I]: Ignore
   - [S]: Skip
   - [angka 1-9]: Match dengan SBR yang muncul sesuai nomornya.

---

## Lisensi / License

Dilisensikan di bawah Lisensi MIT.
*Licensed under the MIT License.*

```text
Copyright (c) 2026 BPS Tabalong

Izin diberikan secara cuma-cuma kepada siapa pun yang memperoleh salinan perangkat lunak ini untuk menggunakannya tanpa batasan, termasuk hak untuk memodifikasi, menyatukan, dan mendistribusikan, dengan ketentuan mencantumkan atribusi hak cipta di atas. Perangkat lunak disediakan "sebagaimana adanya", tanpa jaminan apa pun.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files, to deal in the Software without restriction, subject to including the above copyright notice. The software is provided "as is", without warranty of any kind.
```

---

<p align="center">Made with love, Gilang Wahyu Prasetyo &copy; 2026 BPS Tabalong</p>