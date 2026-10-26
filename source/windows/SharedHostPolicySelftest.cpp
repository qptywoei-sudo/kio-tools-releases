#include "SharedHostPolicy.h"
#include <cassert>
#include <iostream>
using J=nlohmann::json;
int main(){
 using namespace SharedHostPolicy;
 assert(shortcut("recordArea")=="recordArea");assert(captureShortcut("aiTranslate"));assert(captureShortcut("areaCapture"));assert(!captureShortcut("recordArea"));assert(!captureShortcut("recordToggle"));assert(message(J{{"action","shortcutError"}})=="shortcutError");
 for(auto name:{"home","image","pdf","signature","capture","record","web","codes","files","organize","media","phone","settings"})assert(category(name));
 for(auto value:{"","browser","legacy","https://example.com","');alert(1)//"})assert(!category(value));
 assert(shortcut("areaCapture")=="areaCapture");assert(shortcut("fullCapture")=="fullCapture");assert(shortcut("webCapture")=="webCapture");assert(shortcut("recordToggle")=="recordToggle");assert(shortcut("toggleRecording")=="recordToggle");assert(shortcut("arbitrary").empty());
 std::string origin="http://127.0.0.1:4324";
 assert(toolsSource(origin+"/tools/",origin));assert(toolsSource(origin+"/tools/?language=ko",origin));assert(toolsSource(origin+"/tools/#capture",origin));
 for(auto uri:{"http://127.0.0.1:4323/tools/","http://localhost:4324/tools/","http://127.0.0.1:4324/tools/evil","http://127.0.0.1:4324/tools-evil/","https://admin.example/tools/","http://127.0.0.1:4324/health"})assert(!toolsSource(uri,origin));
 for(auto action:{"surfaceReady","desktopReady","driveConnected","captureStarted","captureReady","captureClosed","captureCancelled"})assert(message(J{{"action",action}})==action);
 assert(message(J{{"action","driveConnected"},{"url","https://example.com"}}).empty());
 assert(message(J{{"action","quit"}}).empty());assert(message(J{{"action","captureReady"},{"path","C:/anything"}}).empty());assert(message(J{{"action",42}}).empty());assert(message(J::array({"captureReady"})).empty());
 J fit={{"action","captureFit"},{"width",693},{"height",506},{"chromeHeight",88}};assert(captureFit(fit));
 for(auto key:{"width","height"}){auto invalid=fit;invalid[key]=0;assert(!captureFit(invalid));invalid[key]=64001;assert(!captureFit(invalid));invalid[key]=10.5;assert(!captureFit(invalid));}
 auto invalidFit=fit;invalidFit["width"]=10000;invalidFit["height"]=10000;assert(!captureFit(invalidFit));invalidFit=fit;invalidFit["chromeHeight"]=601;assert(!captureFit(invalidFit));invalidFit=fit;invalidFit["extra"]=true;assert(!captureFit(invalidFit));
 auto compact=fitCaptureSize(693,506,40,120,1500,850,420,260);assert(compact.width==733&&compact.height==626);
 auto portrait=fitCaptureSize(900,1600,40,120,1500,850,420,260);assert(portrait.width<480&&portrait.height==850);
 auto landscape=fitCaptureSize(3840,2160,40,120,1500,850,420,260);assert(landscape.width<=1500&&landscape.height<=850);
 auto tiny=fitCaptureSize(40,40,40,120,1500,850,420,260);assert(tiny.width==420&&tiny.height==260);
 auto smallMonitor=fitCaptureSize(3840,2160,40,120,350,230,420,260);assert(smallMonitor.width<=350&&smallMonitor.height<=230);
 std::string id="d58e838c-81b3-465f-96aa-05501bd6c3fc";
 J copy={{"action","copyText"},{"text","한국어 English Tiếng Việt 日本語 中文"},{"requestId",id}};assert(copyText(copy));
 auto badCopy=copy;badCopy["text"]=std::string(48001,'A');assert(!copyText(badCopy));
 badCopy=copy;badCopy["text"]=std::string("a\0b",3);assert(!copyText(badCopy));
 badCopy=copy;badCopy["requestId"]="fake";assert(!copyText(badCopy));
 badCopy=copy;badCopy["extra"]=true;assert(!copyText(badCopy));
 badCopy=copy;badCopy["text"]=42;assert(!copyText(badCopy));
 badCopy=copy;badCopy["text"]="";assert(copyText(badCopy));
 J identity={{"deviceId",id}};
 J valid={{"token",std::string(64,'A')},{"origin",origin},{"deviceId",id},{"ownerId","desktop"},{"version","4.6.23"},{"clientName","GalaxyControl"}};
 assert(credential(valid,identity,origin,"4.6.23"));
 auto bad=valid;bad["token"]=std::string(31,'A');assert(!credential(bad,identity,origin,"4.6.23"));
 bad=valid;bad["token"]=std::string(257,'A');assert(!credential(bad,identity,origin,"4.6.23"));
 bad=valid;bad["token"]=std::string(63,'A')+"'";assert(!credential(bad,identity,origin,"4.6.23"));
 bad=valid;bad["origin"]="http://127.0.0.1:4323";assert(!credential(bad,identity,origin,"4.6.23"));
 bad=valid;bad["ownerId"]="ADMIN";assert(!credential(bad,identity,origin,"4.6.23"));
 bad=valid;bad["clientName"]="Browser";assert(!credential(bad,identity,origin,"4.6.23"));
 bad=valid;bad["version"]="4.1.0";assert(!credential(bad,identity,origin,"4.6.23"));
 bad=valid;bad["deviceId"]="untrusted";assert(!credential(bad,identity,origin,"4.6.23"));
 bad=valid;bad["extra"]="secret";assert(!credential(bad,identity,origin,"4.6.23"));
 assert(!credential(valid,J{{"deviceId","ba0b0b0c-81b3-465f-96aa-05501bd6c3fc"}},origin,"4.6.23"));
 for(auto key:{"token","origin","deviceId","ownerId","version","clientName"}){bad=valid;bad[key]=true;assert(!credential(bad,identity,origin,"4.6.23"));}
 CaptureVisibility direct;bool shown=false;
 direct.started(true);direct.started(false);assert(direct.pending&&direct.wasVisible);
 assert(direct.finish("captureReady",shown)&&shown);
 assert(direct.finish("captureClosed",shown)&&!shown&&!direct.pending);
 direct.started(true);assert(direct.finish("captureCancelled",shown)&&shown);
 assert(direct.begin(false));direct.started(true);assert(!direct.wasVisible);
 assert(direct.finish("captureCancelled",shown)&&!shown);
 assert(!direct.finish("captureReady",shown));
 CaptureVisibility repeat;bool resultVisible=false;
 assert(repeat.begin(true));assert(!repeat.begin(true));
 assert(repeat.finish("captureReady",resultVisible)&&repeat.ready);
 assert(repeat.begin(true)&&!repeat.ready);assert(!repeat.begin(true));
 assert(repeat.finish("captureReady",resultVisible));assert(repeat.begin(false));
 assert(repeat.finish("captureCancelled",resultVisible)&&!resultVisible&&!repeat.pending);
 CaptureVisibility state;bool visible=false;
 assert(!state.finish("captureReady",visible));
 assert(state.begin(false));assert(!state.begin(true));assert(!state.wasVisible);
 assert(state.finish("captureReady",visible)&&visible&&state.pending);
 assert(state.finish("captureClosed",visible)&&!visible&&!state.pending);
 assert(!state.finish("captureClosed",visible));
 assert(state.begin(true));assert(state.finish("captureCancelled",visible)&&visible&&!state.pending);
 assert(state.begin(false));assert(!state.finish("other",visible)&&state.pending);state.reset();assert(!state.pending&&!state.wasVisible);
 assert(!state.closeWindow());assert(state.begin(false));assert(state.closeWindow());assert(!state.pending&&!state.wasVisible);assert(state.begin(true));assert(state.finish("captureReady",visible)&&visible);assert(state.closeWindow());assert(!state.finish("captureClosed",visible));assert(state.begin(false));assert(state.finish("captureReady",visible)&&visible);assert(state.finish("captureClosed",visible)&&!visible);
 std::cout<<"SharedHost policy: category/shortcut allowlists, trusted origin, private credential, text clipboard contract, capture visibility passed\n";
}
