// frontend/src/pages/Upload.jsx
import { useState } from "react";

export default function Upload() {
  const [file, setFile] = useState(null);
  const [collection, setCollection] = useState("plcnext");
  const [status, setStatus] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file) {
      setStatus("กรุณาเลือกไฟล์ก่อนอัปโหลด");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);
    formData.append("collection", collection);

    try {
      const res = await fetch("/api/upload", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      if (res.ok) {
        setStatus("✅ อัปโหลดสำเร็จแล้ว!");
      } else {
        setStatus("❌ " + (data.error || "อัปโหลดไม่สำเร็จ"));
      }
    } catch (err) {
      setStatus("❌ ข้อผิดพลาด: " + err.message);
    }
  };

  return (
    <div className="container">
      <h1>📁 อัปโหลดเอกสาร</h1>
      <form onSubmit={handleSubmit}>
        <input
          type="file"
          accept=".pdf,.txt,.csv,.json"
          onChange={(e) => setFile(e.target.files[0])}
        />
        <br />
        <input
          type="text"
          placeholder="ชื่อ collection (เช่น plcnext)"
          value={collection}
          onChange={(e) => setCollection(e.target.value)}
        />
        <br />
        <button type="submit">อัปโหลด</button>
      </form>
      <p>{status}</p>
    </div>
  );
}
