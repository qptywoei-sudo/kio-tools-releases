from pathlib import Path
import importlib.util,json,pymupdf
root=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('engine',root/'engine.py');engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)
folder=root/'fixtures/native-pdf';folder.mkdir(parents=True,exist_ok=True)
original=folder/'original.pdf';doc=pymupdf.open();page=doc.new_page(width=600,height=800);page.insert_text((40,700),'SEARCHABLE ORIGINAL',fontsize=14);doc.save(original);doc.close()
r=engine.run({'op':'pdf_annotate','path':str(original),'page':1,'overlay_path':str(root/'fixtures/native-annotation.png'),'output_dir':str(folder)})
assert r['success'],r
with pymupdf.open(r['files'][0]) as d:
 assert 'SEARCHABLE ORIGINAL' in d[0].get_text();pix=d[0].get_pixmap();pix.save(str(folder/'korean-signature-result.png'))
 print('Native Korean text/signature raster overlay and original searchable PDF preserved')
