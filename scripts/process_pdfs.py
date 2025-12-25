import os
import json
import re
import PyPDF2

# DIRECTORIES
UPLOAD_DIR = 'uploads'
TESTS_DIR = 'tests'
MANIFEST_FILE = 'tests/test_manifest.json'

def extract_text_from_pdf(pdf_path):
    text = ""
    try:
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                # Remove Page Numbers (e.g., [24], [1], --- PAGE 2 ---)
                page_text = re.sub(r'\[\d+\]', '', page_text)
                page_text = re.sub(r'---\s*PAGE\s*\d+\s*---', '', page_text)
                text += page_text + "\n"
    except Exception as e:
        print(f"❌ Error reading {pdf_path}: {e}")
    return text

def clean_garbage_text(text):
    """Removes the repetitive header/footer text found in Forum IAS PDFs."""
    
    # 1. Remove the long address/contact footer
    # Matches "Forum Learning Centre : Delhi ... helpdesk@forumias.academy"
    address_pattern = r'Forum\s+Learning\s+Centre\s*:.*?(?:helpdesk@forumias\.academy|admissions@forumias\.academy)'
    text = re.sub(address_pattern, '', text, flags=re.IGNORECASE | re.DOTALL)

    # 2. Remove the Test Code Header
    # Matches "SFG 2026 | Level 1 | Test - #1 ... Test Code: 321101"
    header_pattern = r'SFG\s+2026\s*\|\s*Level\s+\d+\s*\|\s*Test.*?(?:Forum\s*IAS|ForumIAS)'
    text = re.sub(header_pattern, '', text, flags=re.IGNORECASE)

    return text

def format_explanation(text):
    """
    Inserts HTML formatting into the raw explanation text to improve readability.
    """
    if not text: return "No explanation provided."

    # 1. Bold specific keywords and add line breaks before them
    keywords = [
        "Statement I is correct", "Statement II is correct", 
        "Statement 1 is correct", "Statement 2 is correct",
        "Statement I is incorrect", "Statement II is incorrect",
        "Statement 1 is incorrect", "Statement 2 is incorrect",
        "Hence option .*? is correct", "Thus,", "Therefore,"
    ]
    
    for kw in keywords:
        # (?i) makes it case insensitive
        # We replace "Statement..." with "<br><br><b>Statement...</b>"
        pattern = f"(?i)({kw})"
        text = re.sub(pattern, r'<br><br><b>\1</b>', text)

    # 2. Handle numbered lists in explanations (e.g., "1. It is a... 2. It is b...")
    # Look for a number followed by a dot and a space, preceded by whitespace
    text = re.sub(r'\n\s*(\d+\.)\s+', r'<br><b>\1</b> ', text)

    # 3. Clean up multiple <br>
    text = text.replace('<br><br><br>', '<br><br>')
    
    return text

def parse_forum_ias(text):
    # Step 1: Clean the noise globally
    text = clean_garbage_text(text)
    
    questions = []
    
    # Split by "Q.<number>)" or "Q.<number>."
    blocks = re.split(r'\nQ\.\s*\d+[\)\.]', text)
    
    if len(blocks) > 0:
        blocks = blocks[1:]

    for idx, block in enumerate(blocks):
        try:
            block = block.strip()
            
            # EXTRACT ANSWER
            ans_match = re.search(r'(?:Ans|Answer)[\)\:]\s*([a-dA-D])', block)
            correct_char = ans_match.group(1).lower() if ans_match else None
            ans_map = {'a': 0, 'b': 1, 'c': 2, 'd': 3}
            correct_idx = ans_map.get(correct_char, -1)

            # EXTRACT METADATA
            subj_match = re.search(r'Subject:\)\s*(.*)', block)
            subject = subj_match.group(1).strip() if subj_match else "General"

            topic_match = re.search(r'Topic:\)\s*(.*)', block)
            topic = topic_match.group(1).strip() if topic_match else "GS"

            # EXTRACT EXPLANATION
            exp_match = re.search(r'(?:Exp|Explanation)[\)\:]\s*(.*)', block, re.DOTALL | re.IGNORECASE)
            explanation = exp_match.group(1).strip() if exp_match else ""
            
            # Clean metadata from explanation
            explanation = re.sub(r'(Subject:\)|Topic:\)|Source:\)).*', '', explanation, flags=re.DOTALL).strip()
            
            # --- APPLY FORMATTING TO EXPLANATION ---
            explanation = format_explanation(explanation)

            # EXTRACT QUESTION TEXT & OPTIONS
            opt_start = re.search(r'\n\s*a[\)\.]', block)
            q_text = ""
            options = []
            
            if opt_start:
                q_text = block[:opt_start.start()].strip()
                end_of_opts = ans_match.start() if ans_match else len(block)
                opts_block = block[opt_start.start():end_of_opts]
                
                opt_matches = list(re.finditer(r'(?:^|\n)\s*([a-dA-D])[\)\.]', opts_block))
                for i in range(len(opt_matches)):
                    start = opt_matches[i].end()
                    end = opt_matches[i+1].start() if i + 1 < len(opt_matches) else len(opts_block)
                    options.append(opts_block[start:end].strip())
            else:
                q_text = "Error parsing question text."
                options = ["Error", "Error", "Error", "Error"]

            q_obj = {
                "id": idx + 1,
                "text": q_text,
                "options": options,
                "correctAnswer": correct_idx,
                "explanation": explanation,
                "subject": subject,
                "topic": topic
            }
            questions.append(q_obj)

        except Exception as e:
            print(f"Error parsing Q{idx+1}: {e}")

    return questions

def update_manifest(filename, test_name):
    manifest = []
    if os.path.exists(MANIFEST_FILE):
        try:
            with open(MANIFEST_FILE, 'r') as f:
                manifest = json.load(f)
        except:
            manifest = []

    found = False
    for entry in manifest:
        if entry['filename'] == filename:
            entry['name'] = test_name
            found = True
            break
    
    if not found:
        manifest.append({"name": test_name, "filename": filename})

    with open(MANIFEST_FILE, 'w') as f:
        json.dump(manifest, f, indent=2)

def main():
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR)
        return
    if not os.path.exists(TESTS_DIR):
        os.makedirs(TESTS_DIR)

    for f in os.listdir(UPLOAD_DIR):
        if f.endswith('.pdf'):
            print(f"Processing {f}...")
            text = extract_text_from_pdf(os.path.join(UPLOAD_DIR, f))
            questions = parse_forum_ias(text)
            
            if questions:
                out_name = f.replace('.pdf', '.json')
                with open(os.path.join(TESTS_DIR, out_name), 'w') as out_f:
                    json.dump(questions, out_f, indent=2)
                
                update_manifest(out_name, f.replace('.pdf', '').replace('-', ' '))
                print(f"✅ Generated {out_name}")
                os.remove(os.path.join(UPLOAD_DIR, f))

if __name__ == "__main__":
    main()
