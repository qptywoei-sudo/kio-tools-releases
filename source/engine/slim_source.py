import tarfile
from pathlib import Path
original=Path('work/engine/downloads/pymupdf-1.28.2.tar.gz');target=original.with_name('pymupdf-1.28.2-source.tar.gz')
with tarfile.open(original) as src,tarfile.open(target,'w:gz',compresslevel=9) as dst:
 for member in src.getmembers():
  if '/tests/resources/' in member.name:continue
  dst.addfile(member,src.extractfile(member) if member.isfile() else None)
print('Corresponding Python PDF sources without optional test data:',target.stat().st_size)
