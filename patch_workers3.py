import sys

path = 'src/modules/cleaner/workers.py'
code = open(path, 'r', encoding='utf-8').read()

old_part = """                        results_dict = self.classifier.classify_file(fp)
                        for g_name, conf in results_dict.items():
                            conf_pct = conf * 100.0
                            if conf_pct >= self.threshold:
                                if g_name not in results:
                                    results[g_name] = []
                                    groups_found += 1
                                results[g_name].append({
                                    "path": fp,
                                    "size": size,
                                    "confidence": conf_pct,
                                    "type": "general"
                                })"""

new_part = """                        results_dict = self.classifier.classify_file(fp)
                        for g_name, conf_data in results_dict.items():
                            if isinstance(conf_data, dict):
                                conf = conf_data["score"]
                                bbox = conf_data.get("bbox")
                            else:
                                conf = conf_data
                                bbox = None
                            
                            conf_pct = conf * 100.0
                            if conf_pct >= self.threshold:
                                if g_name not in results:
                                    results[g_name] = []
                                    groups_found += 1
                                member = {
                                    "path": fp,
                                    "size": size,
                                    "confidence": conf_pct,
                                    "type": "general"
                                }
                                if bbox is not None:
                                    member["matched_bbox"] = list(bbox)
                                results[g_name].append(member)"""

if old_part in code:
    code = code.replace(old_part, new_part)
    open(path, 'w', encoding='utf-8').write(code)
    print("Replaced!")
else:
    print("Not found.")
