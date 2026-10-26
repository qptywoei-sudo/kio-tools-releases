#include "NativeProtocol.h"
#include <cassert>
#include <iostream>
int main(){
 using J=nlohmann::json;
 for(auto s:{"192.168.1.6:37123","10.0.0.2:5555","172.16.0.9:1234","172.31.255.255:65535","169.254.4.0:1","127.0.0.1:5555"})assert(NativeProtocol::phoneAddress(s));
 for(auto s:{"8.8.8.8:5555","172.32.0.1:5555","192.169.1.1:5555","0.0.0.0:5555","192.168.1.2:0","192.168.1.2:65536","192.168.1:5555","192.168.0010.1:1","192.168.1.1:1;calc","localhost:5555","[::1]:5555"})assert(!NativeProtocol::phoneAddress(s));
 assert(NativeProtocol::phoneArguments("phone.status",J::object()));
 assert(!NativeProtocol::phoneArguments("phone.status",J{{"command","adb"}}));
 assert(NativeProtocol::phoneArguments("phone.pair",J{{"address","192.168.1.6:37123"},{"code","001234"}}));
 assert(!NativeProtocol::phoneArguments("phone.pair",J{{"address","192.168.1.6:37123"},{"code","12345a"}}));
 assert(!NativeProtocol::phoneArguments("phone.pair",J{{"address","example.com:443"},{"code","123456"}}));
 assert(NativeProtocol::phoneArguments("phone.start",J{{"serial","R3CW806NV0B"},{"keyboard","uhid"},{"mouse","sdk"},{"audio","aac"},{"clipboard",false}}));
 assert(!NativeProtocol::phoneArguments("phone.start",J{{"serial","--help"}}));
 assert(!NativeProtocol::phoneArguments("phone.start",J{{"serial","device"},{"clipboard","yes"}}));
 assert(!NativeProtocol::phoneArguments("phone.start",J{{"serial","device"},{"audio","microphone"}}));
 assert(!NativeProtocol::phoneArguments("phone.start",J{{"serial","device"},{"shell",true}}));
 assert(!NativeProtocol::phoneArguments("phone.keyboard",J{{"serial","device\n"}}));
 assert(NativeProtocol::operations().count("phone.connect")&&NativeProtocol::operations().count("phone.stop"));
 std::cout<<"PASS: phone private endpoints, bounded types, pair code, known operations and argument allowlists (no Windows/ADB execution)\n";
}
