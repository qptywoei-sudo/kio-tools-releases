"""Anonymous bounded Google Drive download transport shared with KIO updater."""
import urllib.request,urllib.parse,urllib.error,http.cookiejar
from html.parser import HTMLParser
from update_security import allowed_url
VERSION="publisher"

class SafeRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  if not allowed_url(newurl):raise ValueError('updateNetwork')
  return super().redirect_request(req,fp,code,msg,headers,newurl)
class DownloadForm(HTMLParser):
 def __init__(self):super().__init__();self.action='';self.fields={};self.active=False
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  if tag=='form' and attrs.get('id')=='download-form':self.action=attrs.get('action','');self.active=True
  if self.active and tag=='input' and attrs.get('type')=='hidden' and attrs.get('name'):self.fields[attrs['name']]=attrs.get('value','')
 def handle_endtag(self,tag):
  if tag=='form':self.active=False

def download_response(url):
 if not allowed_url(url):raise ValueError('updateInvalidManifest')
 opener=urllib.request.build_opener(SafeRedirect(),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
 response=opener.open(urllib.request.Request(url,headers={'User-Agent':'KIO-Control-Updater/'+VERSION}),timeout=30)
 # Drive's own large-file confirmation is parsed only for a signed, pinned download URL.
 if 'text/html' in response.headers.get('Content-Type',''):
  page=response.read(1024*1024);response.close();form=DownloadForm();form.feed(page.decode(errors='replace'))
  if not form.action or not allowed_url(form.action) or urllib.parse.urlparse(form.action).hostname!='drive.usercontent.google.com':raise ValueError('updateDriveAccess')
  response=opener.open(form.action+'?'+urllib.parse.urlencode(form.fields),timeout=30)
  if 'text/html' in response.headers.get('Content-Type',''):response.close();raise ValueError('updateDriveAccess')
 return response
