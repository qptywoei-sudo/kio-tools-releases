#include "ShortcutModel.h"
#include <cassert>
#include <iostream>
int main(){
 using namespace ShortcutModel;
 std::vector<Key> desired(5);const char*names[]={"Control+Shift+A","Control+Shift+F","Control+Shift+W","Control+Shift+R","Control+Shift+T"};
 for(int i=0;i<5;++i)assert(parse(names[i],desired[i]));
 std::vector<size_t> calls;
 auto active=recover(desired,{true,false,false,false,false},[&](size_t i,const Key&){calls.push_back(i);return i!=2;});
 assert((calls==std::vector<size_t>{1,2,3,4}));assert(active[0]&&active[1]&&!active[2]&&active[3]&&active[4]);
 calls.clear();active=recover(desired,active,[&](size_t i,const Key&){calls.push_back(i);return true;});assert((calls==std::vector<size_t>{2}));
 calls.clear();active=recover(desired,active,[&](size_t i,const Key&){calls.push_back(i);return true;});assert(calls.empty());
 desired[4].enabled=false;active[4]=false;active=recover(desired,active,[&](size_t i,const Key&){calls.push_back(i);return true;});assert(!active[4]&&calls.empty());
 std::cout<<"PASS: all five background shortcuts recover independently, conflicts do not disable AI, disabled bindings stay off, active bindings are retained\n";
}
