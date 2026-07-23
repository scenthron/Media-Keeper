import sys

path = 'src/modules/cleaner/logic_ai_classifier.py'
code = open(path, 'r', encoding='utf-8').read()

old_part = """                        neg_mapped = (max_neg - 0.35) / (0.85 - 0.35)
                        neg_mapped = max(0.0, min(1.0, float(neg_mapped)))
                        mapped_score = max(0.0, mapped_score - (neg_mapped * 0.5))
                        
                    if mapped_score > 0:
                        result[group_name] = mapped_score"""

new_part = """                        neg_mapped = (max_neg - 0.35) / (0.85 - 0.35)
                        neg_mapped = max(0.0, min(1.0, float(neg_mapped)))
                        mapped_score = max(0.0, mapped_score - (neg_mapped * 0.5))
                        
                    if mapped_score > 0:
                        result[group_name] = {"score": mapped_score, "bbox": matched_bbox}"""

if old_part in code:
    code = code.replace(old_part, new_part)
    open(path, 'w', encoding='utf-8').write(code)
    print("Replaced!")
else:
    print("Not found.")
