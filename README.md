# Smart Assistant for PLCnext (แชทบอท PLCnext)

โปรเจกต์นี้คือระบบผู้ช่วยอัจฉริยะ (Chatbot) สำหรับตอบคำถามทางเทคนิคที่เกี่ยวข้องกับ **PLCnext Technology** จาก Phoenix Contact โดยใช้สถาปัตยกรรม **RAG (Retrieval-Augmented Generation)**

## 🚀 คุณสมบัติเด่น (Features)

* **RAG Pipeline:** ค้นหาคำตอบจากฐานข้อมูลเอกสารคู่มือ PLCnext โดยตรง
* **Multi-modal Input:** รองรับการป้อนข้อมูลหลายรูปแบบ (Text, Image/OCR, Voice/ASR)
* **Local LLM:** ทำงานแบบ Offline-first โดยใช้ `LLaMA 3` ผ่าน `Ollama`
* **Web Interface:** หน้าตาแชทที่ใช้งานง่าย สร้างด้วย React

## 🛠️ เทคโนโลยีที่ใช้ (Tech Stack)

* **Frontend:** React (Vite)
* **Backend:** FastAPI (Python)
* **Database:** PostgreSQL + `pgvector`
* **Orchestration/AI:** LangChain
* **LLM Service:** Ollama (LLaMA 3)
* **Deployment:** Docker Compose

---

## 1. ⚙️ การตั้งค่าเครื่อง (Prerequisites)

ก่อนเริ่มต้น คุณต้องติดตั้งโปรแกรมต่อไปนี้บนเครื่องของคุณ:

1.  **Docker Desktop:** (หรือ Docker Engine + Docker Compose)

## 2. 📦 การติดตั้งโปรเจกต์ (Installation)

```bash
git clone [Your-GitHub-Repo-URL]
cd chatbotplcnext