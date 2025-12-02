#!/usr/bin/env python3
"""แก้ไข main.py - แยก retrieval query กับ LLM context"""

def fix_main_py(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if 'question=combined_message,' in content and 'combined_message = message' in content:
        # แทนที่ combined_message = message
        content = content.replace(
            '    combined_message = message\n    if history_context:\n        combined_message = f"[Previous conversation]\\n{history_context}\\n[Current question]\\n{message}"',
            '''    # ✅ FIX v2.7: แยก retrieval query กับ LLM context
    retrieval_query = message
    llm_context = message
    if history_context:
        llm_context = f"[Previous conversation]\\n{history_context}\\n[Current question]\\n{message}"'''
        )
        
        # แทนที่ file_text section
        content = content.replace(
            '    if file_text:\n        truncated_file_text = file_text[:DEEP_MODE_CHARS] if len(file_text) > DEEP_MODE_CHARS else file_text\n        combined_message = f"{combined_message}\\n\\n--- File Content ({file.filename}) ---\\n{truncated_file_text}"',
            '''    if file_text:
        truncated_file_text = file_text[:DEEP_MODE_CHARS] if len(file_text) > DEEP_MODE_CHARS else file_text
        retrieval_query = f"{message}\\n\\n--- File Content ({file.filename}) ---\\n{truncated_file_text}"
        llm_context = f"{llm_context}\\n\\n--- File Content ({file.filename}) ---\\n{truncated_file_text}"'''
        )
        
        # แทนที่ question=combined_message
        content = content.replace(
            'question=combined_message,',
            'question=retrieval_query,  # ✅ ใช้แค่คำถาม ไม่รวม history'
        )
        
        print("✅ Fixed main.py successfully!")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    else:
        print("⚠️ Pattern not found")
        return False

if __name__ == "__main__":
    fix_main_py("backend/main.py")
