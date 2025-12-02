#!/usr/bin/env python3
"""แก้ไข ask_llm_directly() ใน main.py"""

def fix_main_py(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if 'You are a helpful AI assistant that can answer questions on ANY topic' in content:
        # แทนที่ prompt
        content = content.replace(
            'You are a helpful AI assistant that can answer questions on ANY topic.',
            'You are Panya, a helpful AI assistant. IMPORTANT: PLCnext is made by Phoenix Contact (NOT Siemens, NOT Schneider Electric!).'
        )
        content = content.replace(
            '7. You can discuss ANY topic - technology, science, entertainment, business, etc.',
            '7. If asked about PLCnext/PLC details, say "กรุณาใช้โหมด 🔍 Deep เพื่อค้นหาข้อมูลที่ถูกต้อง / Please use 🔍 Deep mode for accurate PLCnext information". NEVER say PLCnext is made by Siemens or Schneider!'
        )
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print("✅ Fixed!")
        return True
    else:
        print("⚠️ Already fixed or pattern not found")
        return False

if __name__ == "__main__":
    fix_main_py("backend/main.py")
