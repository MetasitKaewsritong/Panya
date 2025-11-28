# Smart Assistant for PLCnext (แชทบอท PLCnext)

โปรเจกต์นี้คือระบบผู้ช่วยอัจฉริยะ (Chatbot) สำหรับตอบคำถามทางเทคนิคที่เกี่ยวข้องกับ **PLCnext Technology** จาก Phoenix Contact โดยใช้สถาปัตยกรรม **RAG (Retrieval-Augmented Generation)**

แชทบอทนี้ถูกออกแบบมาเพื่อลดเวลาในการค้นหาข้อมูลในคู่มือที่ซับซ้อน ช่วยให้วิศวกรและช่างเทคนิคสามารถแก้ไขปัญหาและรับคำแนะนำได้รวดเร็วขึ้น

## 🚀 คุณสมบัติเด่น (Features)

* **RAG Pipeline:** ค้นหาคำตอบจากฐานข้อมูลเอกสารคู่มือ PLCnext โดยตรง เพื่อให้ได้คำตอบที่แม่นยำและอ้างอิงได้
* **Multi-modal Input:** รองรับการป้อนข้อมูลหลายรูปแบบ:
    * **Text:** พิมพ์คำถามโดยตรง
    * **Image (OCR):** อัปโหลดรูปภาพ (เช่น Error Code บนหน้าจอ) เพื่อให้ระบบวิเคราะห์
    * **Voice (ASR):** พูดคำถามผ่านไมโครโฟน (ใช้ Whisper)
* **Multi-file Upload:** รองรับการอัปโหลดไฟล์หลายประเภท:
    * **รูปภาพ:** PNG, JPG, GIF, WebP (ใช้ OCR อ่านข้อความ)
    * **เสียง:** MP3, WAV, M4A, WebM (ใช้ Whisper แปลงเป็นข้อความ)
    * **เอกสาร:** PDF, TXT, CSV, JSON, DOCX
* **GPU Acceleration:** รองรับ NVIDIA GPU เพื่อเพิ่มความเร็วในการประมวลผล
* **Streaming Response:** แสดงคำตอบแบบ real-time ทีละคำ (ไม่ต้องรอจนเสร็จ)
* **Local LLM:** ทำงานแบบ Offline-first โดยใช้ `LLaMA 3` ผ่าน `Ollama` ทำให้ข้อมูลปลอดภัยและไม่ต้องเชื่อมต่ออินเทอร์เน็ต
* **Web Interface:** หน้าตาแชทที่ใช้งานง่าย สร้างด้วย React

## 🛠️ เทคโนโลยีที่ใช้ (Tech Stack)

* **Frontend:** React (Vite)
* **Backend:** FastAPI (Python)
* **Database:** PostgreSQL + `pgvector` (สำหรับ Vector Storage)
* **Orchestration/AI:** LangChain
* **LLM Service:** Ollama (LLaMA 3)
* **Deployment:** Docker Compose

---

## 🏁 การติดตั้งและรันโปรเจกต์ (Installation Guide)

นี่คือขั้นตอนทั้งหมดสำหรับผู้ที่ติดตั้งครั้งแรก เพื่อให้ระบบทำงานได้ครบถ้วน

### 1. ⚙️ การตั้งค่าเครื่อง (Prerequisites)

ก่อนเริ่มต้น คุณต้องติดตั้งโปรแกรมต่อไปนี้บนเครื่องของคุณ:

1.  **Docker Desktop:** (หรือ Docker Engine + Docker Compose) สำหรับการรันโปรเจกต์ทั้งหมดใน Container

### 2. 📦 การติดตั้งโปรเจกต์ (Installation)

1.  **Clone a repository:**
    ```bash
    git clone [Your-GitHub-Repo-URL]
    cd chatbotplcnext 
    ```
    *(หมายเหตุ: หากคุณ clone มาแล้ว ให้ข้ามไป)*

### 3. 🔑 (สำคัญ!) การตั้งค่า Environment

โปรเจกต์นี้ต้องใช้ไฟล์ `.env` ในการกำหนดค่า Backend

1.  **สร้างไฟล์ `.env`:**
    ในโปรเจกต์จะมีไฟล์ `backend/.env.example` (ไฟล์ตัวอย่างที่ปลอดภัย)
    
    คัดลอกไฟล์ตัวอย่างนี้เพื่อสร้างไฟล์ `.env` ที่ระบบจะใช้จริง (ไฟล์นี้จะถูก `.gitignore` ซ่อนไว้):
    ```bash
    cp backend/.env.example backend/.env
    ```

2.  **แก้ไข (ถ้าจำเป็น):**
    * โดยทั่วไป คุณสามารถใช้ค่าเริ่มต้นในไฟล์ `.env` ได้เลย
    * **ยกเว้น** หากคุณต้องการใช้ **OpenAI API** (ซึ่งไม่บังคับ) คุณต้องไปแก้ไขไฟล์ `backend/.env` แล้วกรอก `OPENAI_API_KEY` ของคุณเอง **(ห้ามแชร์คีย์นี้ให้ใครเด็ดขาด!)**

### 4. 🧠 (สำคัญ!) การเตรียมโมเดล LLM

ระบบนี้ใช้ Ollama ในการรัน LLM เราต้องดึงโมเดลที่จำเป็นมารอไว้ก่อน

1.  **สตาร์ทเฉพาะ Ollama:**
    ```bash
    docker compose up -d ollama
    ```

2.  **ดึงโมเดล (Pull Models):**
    รัน 2 คำสั่งนี้เพื่อดึงโมเดลหลัก (`llama3.2`) และโมเดลสำหรับประเมินผล (`phi3:mini`):

    ```bash
    docker compose exec ollama ollama pull llama3.2
    docker compose exec ollama ollama pull phi3:mini
    ```
    *(ขั้นตอนนี้จะใช้เวลาสักครู่ ขึ้นอยู่กับความเร็วอินเทอร์เน็ต)*

### 5. 💾 การกู้คืนฐานข้อมูล (Restoring the Database)

โปรเจกต์นี้มีไฟล์ `backup.sql` ซึ่งเป็นฐานข้อมูลที่ผ่านการ "ย่อย" (Embed) เอกสาร PLCnext มาแล้ว เพื่อให้คุณสามารถเริ่มใช้งานได้ทันทีโดยไม่ต้องรอ Embed ข้อมูลใหม่

1.  **สตาร์ทเฉพาะฐานข้อมูล:**
    ```bash
    docker compose up -d postgres
    ```
    *(คำสั่งนี้จะสร้าง Container ชื่อ `postgres` และรอให้มันทำงาน)*

2.  **นำเข้าข้อมูล (Restore):**
    ```bash
    docker compose exec -T postgres psql -U user plcnextdb < backup.sql
    ```
    *(คำสั่งนี้จะนำข้อมูลจาก `backup.sql` เข้าไปในฐานข้อมูล `plcnextdb` ที่กำลังรันอยู่)*

### 6. 🚀 การรันโปรเจกต์ (Running the Project)

หลังจากเตรียม `.env`, โมเดล Ollama, และฐานข้อมูลแล้ว คุณสามารถสตาร์ทระบบทั้งหมดได้

1.  **Build และ Run:**
    ```bash
    docker compose up --build
    ```
    *(คำสั่งนี้จะสร้าง (build) Image ของ `frontend` และ `backend` และสตาร์ทบริการทั้งหมด: `frontend`, `backend`, `postgres`, และ `ollama`)*

2.  **รอจนระบบพร้อม:** รอจน Log ใน Terminal แสดงว่าทุกบริการทำงาน (running) โดยเฉพาะ `frontend` และ `backend`

3.  **เข้าใช้งาน:**
    เปิดเบราว์เซอร์แล้วไปที่: **[http://localhost:5173](http://localhost:5173)**

---

## ⚡ การเพิ่มประสิทธิภาพ (Performance Optimization)

### 🎮 เปิดใช้งาน GPU (NVIDIA)

หากเครื่องของคุณมี NVIDIA GPU สามารถเพิ่มความเร็วได้ 5-10 เท่า

#### ขั้นตอนที่ 1: ตรวจสอบว่า GPU พร้อมใช้งาน
```bash
# ทดสอบว่า Docker เห็น GPU หรือไม่
docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi
```

#### ขั้นตอนที่ 2: แก้ไข docker-compose.yml

เพิ่มส่วน `deploy` ใน service `ollama`:

```yaml
services:
  ollama:
    image: ollama/ollama:latest
    # ... config อื่นๆ ...
    
    # ⚡ เพิ่มส่วนนี้เพื่อเปิดใช้ GPU
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

#### ขั้นตอนที่ 3: Restart
```bash
docker compose down
docker compose up -d
```

#### ขั้นตอนที่ 4: ตรวจสอบว่า GPU ทำงาน
```bash
docker compose logs ollama | grep -i gpu
```

### 📊 ผลลัพธ์ที่คาดหวัง

| สถานะ | Query สั้น | Query ยาว |
|-------|-----------|-----------|
| CPU Only | ~4-6 วินาที | ~25 วินาที |
| GPU Enabled | ~0.5-1 วินาที | ~3-5 วินาที |

---

## 📁 ประเภทไฟล์ที่รองรับ (Supported File Types)

ระบบรองรับการอัปโหลดไฟล์หลายประเภทผ่านหน้า Chat:

| ประเภท | นามสกุล | วิธีประมวลผล |
|--------|---------|-------------|
| รูปภาพ | PNG, JPG, GIF, WebP | OCR (Tesseract) - อ่านข้อความจากภาพ |
| เสียง | MP3, WAV, M4A, WebM | Whisper - แปลงเสียงเป็นข้อความ |
| PDF | .pdf | PyMuPDF - อ่านเนื้อหาจาก PDF |
| Text | .txt | อ่านข้อความโดยตรง |
| CSV | .csv | อ่านข้อมูลตาราง |
| JSON | .json | Parse และแสดงข้อมูล |
| Word | .docx | python-docx - อ่านเนื้อหาจาก Word |

---

## 7. ➕ การเพิ่มข้อมูลใหม่ (Embedding New Data)

หากคุณต้องการ "เพิ่มความรู้" ให้แชทบอทด้วยไฟล์ PDF, TXT หรือ JSON ของคุณเอง ให้ทำตามขั้นตอนต่อไปนี้

### 7.1 (สำคัญ!) การตั้งค่า Path ใน `docker-compose.yml`

โดยปกติ Docker Container จะ "มองไม่เห็น" ไฟล์ในคอมพิวเตอร์ของคุณ คุณต้อง "อนุญาต" ให้มันเห็นโฟลเดอร์ที่คุณเก็บเอกสารก่อน โดยการแก้ไขไฟล์ `docker-compose.yml`

1.  **วางไฟล์ของคุณ:** นำไฟล์ (เช่น `my_manual.pdf`) ไปวางในโฟลเดอร์ใดก็ได้ในเครื่องของคุณ (เช่น `D:/MyData/PDFs`)

2.  **แก้ไขไฟล์ `docker-compose.yml`:**
    เปิดไฟล์ `docker-compose.yml` ขึ้นมา ค้นหาส่วนของ `backend:` และเพิ่ม `volumes:` (Path) ของคุณลงไป

    **ตัวอย่าง:**
    ```yaml
    services:
      backend:
        # ... (การตั้งค่าอื่นๆ) ...
        volumes:
          - ./backend:/app  # <-- Path นี้ห้ามลบ
          
          # --- เพิ่ม Path ของคุณตรงนี้ ---
          # รูปแบบ: "[Path บนคอมของคุณ]:[Path ที่จะให้ Docker เห็น]"
          
          # ตัวอย่างที่ 1: ถ้าไฟล์อยู่ที่ D:/MyData/PDFs
          - "D:/MyData/PDFs:/app/data/custom_pdfs"
          
          # ตัวอย่างที่ 2: ถ้าไฟล์อยู่ที่ data/raw ภายในโปรเจกต์
          # (อ้างอิงจากคู่มือ)
          - "./data/raw:/app/data/raw" 
          - "./data/Knowledge:/app/data/Knowledge"
    ```
    * **คำอธิบาย:**
        * `D:/MyData/PDFs`: คือ Path จริงบนคอมพิวเตอร์ของคุณ
        * `/app/data/custom_pdfs`: คือ Path ที่ Python (ใน Docker) จะใช้เรียกไฟล์นี้

3.  **รีสตาร์ท Docker:** หลังจากแก้ไข `docker-compose.yml` ให้รัน `docker compose up --build -d` อีกครั้งเพื่อให้การเปลี่ยนแปลงมีผล

### 7.2 รันคำสั่ง Embedding

ใช้ Path **ภายใน Docker** ที่คุณตั้งไว้ใน `volumes` (เช่น `/app/data/custom_pdfs`)

```bash
# ตัวอย่าง: รัน embed ไฟล์ my_manual.pdf ที่อยู่ใน D:/MyData/PDFs
docker compose exec backend python embed.py data/custom_pdfs/manual.pdf

# ตัวอย่าง: รัน embed ไฟล์ในโฟลเดอร์ data/raw (ตามคู่มือ)
docker compose exec backend python embed.py data/raw/my_manual.pdf
```

---

## 🔧 คำสั่งที่ใช้บ่อย (Common Commands)

```bash
# สตาร์ทระบบทั้งหมด
docker compose up -d

# สตาร์ทพร้อม rebuild
docker compose up -d --build

# หยุดระบบ (เก็บ data ไว้)
docker compose down

# หยุดระบบและลบ data ทั้งหมด (ระวัง!)
docker compose down -v

# ดู logs ของ backend
docker compose logs -f backend

# ดู logs ของ ollama
docker compose logs -f ollama

# เข้าไปใน container backend
docker compose exec backend bash
```

---

## ❓ FAQ / Troubleshooting

### Q: Model หายทุกครั้งที่ restart?
**A:** อย่าใช้ `docker compose down -v` เพราะ `-v` จะลบ volumes ทั้งหมด รวมถึง model ที่โหลดไว้ ใช้แค่ `docker compose down` พอ

### Q: ทำไมตอบช้ามาก?
**A:** 
1. ตรวจสอบว่าปิด RAGAS แล้วหรือยัง (ใน `.env` ตั้ง `EVAL_WITH_RAGAS=false`)
2. ถ้ามี NVIDIA GPU ให้เปิดใช้งานตามคู่มือด้านบน

### Q: Upload ไฟล์ PDF แล้ว error?
**A:** ตรวจสอบว่าติดตั้ง `PyMuPDF` ใน `requirements.txt` แล้ว และ rebuild ด้วย `docker compose up -d --build`

---

## 📝 License

MIT License