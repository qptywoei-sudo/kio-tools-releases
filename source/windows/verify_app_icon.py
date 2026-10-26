"""Verify icon bytes in actual PE resource tables without running Windows code."""
from pathlib import Path
import hashlib,io,json,struct
from PIL import Image

def resources(path):
 data=Path(path).read_bytes();u16=lambda at:struct.unpack_from('<H',data,at)[0];u32=lambda at:struct.unpack_from('<I',data,at)[0]
 pe=u32(0x3c);assert data[:2]==b'MZ' and data[pe:pe+4]==b'PE\0\0'
 optional=pe+24;directory=optional+(112 if u16(optional)==0x20b else 96);rva,size=u32(directory+16),u32(directory+20);assert rva and size
 sections=[];section=optional+u16(pe+20)
 for number in range(u16(pe+6)):
  at=section+number*40;sections.append((u32(at+12),max(u32(at+8),u32(at+16)),u32(at+20)))
 def offset(value):
  for va,length,raw in sections:
   if va<=value<va+length:return raw+value-va
  raise ValueError('Resource RVA outside PE sections')
 base=offset(rva);result={}
 def visit(relative,names=()):
  assert relative+16<=size and len(names)<=3;at=base+relative
  for number in range(u16(at+12)+u16(at+14)):
   entry=at+16+number*8;ident,child=u32(entry),u32(entry+4)
   if ident&0x80000000:continue
   path=(*names,ident)
   if child&0x80000000:visit(child&0x7fffffff,path)
   else:
    assert child+16<=size;descriptor=base+child;start=offset(u32(descriptor));length=u32(descriptor+4);assert start+length<=len(data);result[path]=data[start:start+length]
 visit(0);return result

def verify(binary,ico):
 embedded=resources(binary);source=Path(ico).read_bytes();reserved,kind,count=struct.unpack_from('<HHH',source)
 assert reserved==0 and kind==1 and count==9;chunks={}
 for number in range(count):
  width,height,_,_,_,_,length,start=struct.unpack_from('<BBBBHHII',source,6+16*number);chunks[width or 256]=source[start:start+length]
 groups=[(key,data) for key,data in embedded.items() if key[0]==14 and key[1]==1];assert len(groups)==1
 group_key,group=groups[0];reserved,kind,count=struct.unpack_from('<HHH',group);assert reserved==0 and kind==1 and count==len(chunks)
 sizes=[]
 for number in range(count):
  width,height,_,_,_,bits,length,ident=struct.unpack_from('<BBBBHHIH',group,6+14*number);width=width or 256;height=height or 256;data=embedded[(3,ident,group_key[2])]
  assert bits==32 and length==len(data) and data==chunks[width]
  with Image.open(io.BytesIO(data)) as image:assert image.size==(width,height);assert image.mode=='RGBA';assert image.getpixel((0,0))[3]<=2;assert image.getchannel('A').getextrema()==(0,255)
  sizes.append(width)
 return {'binary':str(binary),'resource_group_id':1,'resource_icon_count':count,'sizes':sorted(sizes),'source_icon_sha256':hashlib.sha256(source).hexdigest(),'embedded_resource_bytes_match_source':True,'windows_icon_rendering_executed':False}

if __name__=='__main__':
 root=Path(__file__).resolve().parent;result=verify(root/'GalaxyControl-Integrated.exe',root/'GalaxyControl.ico');(root/'app-icon-pe-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result))
